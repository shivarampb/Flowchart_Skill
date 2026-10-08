"""Minimal, dependency-free Model Context Protocol server core (JSON-RPC 2.0).

Implements the handshake-era MCP revisions 2024-11-05 through 2025-11-25:
lifecycle (initialize / ping), tools, resources (incl. templates) and prompts.
Clients that first probe the stateless ``server/discover`` method of newer
revisions receive "method not found" and fall back to ``initialize``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

LOG = logging.getLogger("iso5807_mcp")

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class ToolError(Exception):
    """Invalid tool input; reported to the model as a tool result with isError=true."""


Content = List[Dict[str, Any]]


@dataclass
class Tool:
    name: str
    title: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Content]

    def definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "title": self.title,
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


@dataclass
class Resource:
    uri: str
    name: str
    title: str
    description: str
    mime_type: str
    read: Callable[[], str]

    def definition(self) -> Dict[str, Any]:
        return {"uri": self.uri, "name": self.name, "title": self.title,
                "description": self.description, "mimeType": self.mime_type}


@dataclass
class ResourceTemplate:
    uri_template: str
    name: str
    title: str
    description: str
    mime_type: str
    read: Callable[[str], Optional[str]]  # receives the variable part; None if unknown
    pattern: "re.Pattern[str]" = field(init=False)

    def __post_init__(self) -> None:
        prefix, _, _ = self.uri_template.partition("{")
        self.pattern = re.compile(re.escape(prefix) + r"(?P<value>[^/]+)$")

    def definition(self) -> Dict[str, Any]:
        return {"uriTemplate": self.uri_template, "name": self.name, "title": self.title,
                "description": self.description, "mimeType": self.mime_type}


@dataclass
class Prompt:
    name: str
    title: str
    description: str
    arguments: List[Dict[str, Any]]
    render: Callable[[Dict[str, str]], str]

    def definition(self) -> Dict[str, Any]:
        return {"name": self.name, "title": self.title, "description": self.description,
                "arguments": self.arguments}


def text_content(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text}


def error_response(msg_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


class McpServer:
    """Transport-independent request dispatcher."""

    def __init__(self, name: str, version: str, title: str, instructions: str,
                 tools: List[Tool], resources: List[Resource],
                 templates: List[ResourceTemplate], prompts: List[Prompt]) -> None:
        self.name = name
        self.version = version
        self.title = title
        self.instructions = instructions
        self.tools = {t.name: t for t in tools}
        self.resources = {r.uri: r for r in resources}
        self.templates = templates
        self.prompts = {p.name: p for p in prompts}
        self._methods: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "initialize": self._initialize,
            "ping": lambda params: {},
            "tools/list": lambda params: {"tools": [t.definition() for t in tools]},
            "tools/call": self._call_tool,
            "resources/list": lambda params: {"resources": [r.definition() for r in resources]},
            "resources/templates/list": lambda params: {
                "resourceTemplates": [t.definition() for t in templates]},
            "resources/read": self._read_resource,
            "prompts/list": lambda params: {"prompts": [p.definition() for p in prompts]},
            "prompts/get": self._get_prompt,
            "logging/setLevel": lambda params: {},
        }

    # -- dispatch ------------------------------------------------------------
    def handle(self, message: Any) -> Any:
        """Handle one decoded JSON-RPC message (or batch); return the response or None."""
        if isinstance(message, list):
            if not message:
                return error_response(None, INVALID_REQUEST, "Invalid Request: empty batch")
            responses = [r for r in (self._handle_one(m) for m in message) if r is not None]
            return responses or None
        return self._handle_one(message)

    def _handle_one(self, message: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            msg_id = message.get("id") if isinstance(message, dict) else None
            return error_response(msg_id, INVALID_REQUEST, "Invalid Request")
        if "method" not in message:
            return None  # a response to a server-initiated request; this server sends none
        method = message["method"]
        is_request = "id" in message
        msg_id = message.get("id")
        if not isinstance(method, str):
            return error_response(msg_id, INVALID_REQUEST, "Invalid Request: method") \
                if is_request else None
        if not is_request:
            LOG.debug("notification %s", method)
            return None
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return error_response(msg_id, INVALID_PARAMS, "params must be an object")
        handler = self._methods.get(method)
        if handler is None:
            return error_response(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        try:
            result = handler(params)
        except JsonRpcError as exc:
            return error_response(msg_id, exc.code, exc.message, exc.data)
        except Exception:  # pragma: no cover - defensive
            LOG.exception("internal error in %s", method)
            return error_response(msg_id, INTERNAL_ERROR, "Internal error")
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # -- methods -------------------------------------------------------------
    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS \
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        client = params.get("clientInfo") or {}
        LOG.info("initialize from %s %s (protocol %s -> %s)", client.get("name"),
                 client.get("version"), requested, version)
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": self.name, "title": self.title, "version": self.version},
            "instructions": self.instructions,
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "arguments must be an object")
        tool = self.tools.get(name) if isinstance(name, str) else None
        if tool is None:
            raise JsonRpcError(INVALID_PARAMS, f"Unknown tool: {name}",
                               {"available": sorted(self.tools)})
        try:
            content = tool.handler(arguments)
        except ToolError as exc:
            return {"content": [text_content(f"Error: {exc}")], "isError": True}
        except Exception as exc:  # pragma: no cover - defensive
            LOG.exception("tool %s failed", name)
            return {"content": [text_content(f"Internal error in {name}: {exc}")],
                    "isError": True}
        return {"content": content, "isError": False}

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise JsonRpcError(INVALID_PARAMS, "uri must be a string")
        resource = self.resources.get(uri)
        if resource is not None:
            return {"contents": [{"uri": uri, "mimeType": resource.mime_type,
                                  "text": resource.read()}]}
        for template in self.templates:
            match = template.pattern.match(uri)
            if match:
                text = template.read(match.group("value"))
                if text is not None:
                    return {"contents": [{"uri": uri, "mimeType": template.mime_type,
                                          "text": text}]}
        raise JsonRpcError(RESOURCE_NOT_FOUND, f"Resource not found: {uri}", {"uri": uri})

    def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        prompt = self.prompts.get(name) if isinstance(name, str) else None
        if prompt is None:
            raise JsonRpcError(INVALID_PARAMS, f"Unknown prompt: {name}",
                               {"available": sorted(self.prompts)})
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "arguments must be an object")
        missing = [a["name"] for a in prompt.arguments
                   if a.get("required") and not str(arguments.get(a["name"], "")).strip()]
        if missing:
            raise JsonRpcError(INVALID_PARAMS,
                               "Missing required argument(s): " + ", ".join(missing))
        text = prompt.render({k: str(v) for k, v in arguments.items()})
        return {"description": prompt.description,
                "messages": [{"role": "user", "content": text_content(text)}]}
