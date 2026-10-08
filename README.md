# ANSI/ISO 5807:1985 Flowchart Skill

A strict guide to the ANSI/ISO 5807:1985 flowchart standard, an analysis of the flowcharting
skill, and a working **MCP server** that serves the standard, validates flowcharts against
it, analyses their logic and renders them as Mermaid. A ready-made **Claude configuration**
wires all of it into Claude Code, Claude Desktop and claude.ai Projects.

| Path | What it is |
|---|---|
| [`docs/ANSI-ISO-5807-Flowchart-Guide.md`](docs/ANSI-ISO-5807-Flowchart-Guide.md) | Part 1: rules and syntax (symbols, flowlines, connectors, text, structure). Part 2: analysis of the skill (abstraction, systemic thinking, granularity, communication). |
| [`mcp_server/`](mcp_server/) | MCP server and CLI, Python ≥ 3.9 standard library only (no installs). |
| [`CLAUDE.md`](CLAUDE.md), [`.claude/`](.claude/), [`.mcp.json`](.mcp.json) | Claude Code configuration: standing instructions, permissions, the `/iso5807-flowchart` skill, MCP server registration. |
| [`integrations/`](integrations/) | Claude Desktop config and claude.ai Project instructions. |
| [`examples/`](examples/) | Sample flowcharts (valid and deliberately flawed). |
| [`tests/`](tests/) | Unit, protocol, transport, docs-consistency and SDK-interoperability tests. |

## Quick start

### Claude Code

```bash
git clone <this repository> && cd Flowchart_Skill
claude
```

- `CLAUDE.md` is loaded as project memory: Claude works as a systems analyst and follows the
  standard and the validation workflow.
- `.mcp.json` registers the `iso5807-flowchart` server and `.claude/settings.json` enables it
  and pre-approves its read-only tools. Claude Code honours those settings once you trust the
  folder; otherwise approve the server when prompted. `/mcp` shows its status.
- Type `/iso5807-flowchart <process description or Mermaid code>`, or simply ask for a
  flowchart; the skill loads automatically.
- On Windows, change `"command": "python3"` to `"python"` (or `"py"`) in `.mcp.json`.

There is no single "`.claude` file": Claude Code reads `CLAUDE.md` (instructions),
`.claude/settings.json` (permissions and enabled servers), `.claude/skills/` (skills) and
`.mcp.json` (MCP servers). All four are included.

### Claude Desktop

Add the server to `claude_desktop_config.json` (Settings → Developer → Edit Config) with
the absolute path of your checkout, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "iso5807-flowchart": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/Flowchart_Skill/mcp_server/server.py"]
    }
  }
}
```

On Windows use `"command": "python"` (or `"py"`) and a path such as
`"C:\\Users\\you\\Flowchart_Skill\\mcp_server\\server.py"`.

### claude.ai Projects

1. Create a Project and paste the text from
   [`integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md`](integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md)
   into **Instructions**.
2. Upload `docs/ANSI-ISO-5807-Flowchart-Guide.md` as **project knowledge**.
3. Optional, for the validation tools: claude.ai connects to remote MCP servers only, so run
   the server over HTTP behind HTTPS and add it as a custom connector (**Settings →
   Connectors → Add custom connector**, URL `https://<your-host>/<path>`):

   ```bash
   python3 mcp_server/server.py --http --host 0.0.0.0 --port 8765 --path /mcp-<random-string>
   ```

   claude.ai connects from Anthropic's cloud, so the endpoint must be publicly reachable over
   HTTPS (reverse proxy or tunnel). Custom connectors authenticate with OAuth or not at all,
   so `--auth-token` cannot be used there; an unguessable `--path` keeps casual callers out.
   The tools are read-only and access no data.

### Any other MCP client

```bash
python3 mcp_server/server.py                      # stdio (default)
python3 mcp_server/server.py --http --port 8765   # Streamable HTTP at http://127.0.0.1:8765/mcp
npx @modelcontextprotocol/inspector python3 mcp_server/server.py   # interactive inspection
```

Optional install as a command: `pip install ./mcp_server` provides `iso5807-mcp`.

### Command line (no MCP client needed)

```bash
python3 mcp_server/server.py validate examples/order-processing.json     # exit 1 on errors
python3 mcp_server/server.py analyze  examples/refund-request.json
python3 mcp_server/server.py mermaid  examples/monthly-billing.json [--classic]
python3 mcp_server/server.py check-mermaid examples/informal-approval.mmd
```

Use `-` instead of a file name to read standard input. Exit codes: 0 conformant, 1 errors
found, 2 unreadable input.

## MCP server

### Tools

All tools are read-only and idempotent.

| Tool | Purpose |
|---|---|
| `iso5807_symbol_reference` | Symbol geometry, meaning, when (not) to use, text and flow conventions, Mermaid shape; filter by symbol, family or chart type. |
| `iso5807_rules` | The rule book: IDs, basis (ISO 5807 or practice), severity, rationale, fix. |
| `validate_flowchart` | Conformance check of a flowchart model; returns `valid` and findings with rule IDs and fixes. `strict: false` accepts ANSI X3.5 legacy symbols and chart-type mixing. |
| `analyze_flowchart` | Loops and exits, redundancy, bottlenecks and single points of failure, missing failure states, abstraction drift; metrics such as cyclomatic complexity and end-to-end paths. |
| `generate_mermaid` | Mermaid code with ISO shapes (`extended`, Mermaid ≥ 11.3) or bracket shapes (`classic`, Mermaid ≥ 10.4), plus validation summary and fidelity notes. |
| `validate_mermaid` | Parses existing Mermaid flowcharts (classic or extended syntax), maps shapes to ISO symbols, reports outline misuse and validates; returns the parsed model. |

**Resources:** `iso5807://guide` (the guide), `iso5807://symbols`, `iso5807://rules`,
`iso5807://chart-types`, `iso5807://schema/flowchart`, `iso5807://examples/<name>`, and the
templates `iso5807://symbols/{symbol_id}` and `iso5807://rules/{rule_id}`.

**Prompts:** `design_flowchart` (process description → validated chart) and
`review_flowchart` (existing chart → findings and corrected chart).

The server also sends instructions at initialization, which clients such as Claude Code add
to the model's context.

### Flowchart model

```json
{
  "title": "Process customer order",
  "chart_type": "program",
  "direction": "TB",
  "nodes": [
    {"id": "start", "type": "terminator", "text": "Start"},
    {"id": "valid", "type": "decision", "text": "Order data valid?"},
    {"id": "ship", "type": "process", "text": "Schedule shipment"},
    {"id": "reject", "type": "data", "text": "Write rejection notice"},
    {"id": "end", "type": "terminator", "text": "End"}
  ],
  "edges": [
    {"from": "start", "to": "valid"},
    {"from": "valid", "to": "ship", "label": "Yes"},
    {"from": "valid", "to": "reject", "label": "No"},
    {"from": "ship", "to": "end"},
    {"from": "reject", "to": "end"}
  ]
}
```

| Field | Values |
|---|---|
| `chart_type` | `program` (default), `data`, `system`, `program_network`, `system_resources` |
| `direction` | `TB` (default) or `LR`; `BT`/`RL` are reported (FLW-01) |
| node `type` | `terminator`, `process`, `predefined_process`, `manual_operation`, `preparation`, `decision`, `parallel_mode`, `loop_limit`, `data`, `stored_data`, `internal_storage`, `sequential_access_storage`, `direct_access_storage`, `document`, `manual_input`, `card`, `punched_tape`, `display`, `connector`, `annotation`, `ellipsis`; legacy `off_page_connector`. Common aliases (`start`, `io`, `diamond`, `subroutine`, …) are accepted. |
| node extras | `role` + `loop_id` (loop limits), `annotates` (annotations), `detail_ref` (striped symbol), `multiple` (stacked data symbols), `off_page` (cross-page connector), `page` |
| edge `kind` | `flow` (default), `dashed`, `communication_link`, `control_transfer` |

The complete JSON schema is the resource `iso5807://schema/flowchart` and part of each tool's
input schema.

### Mermaid support

The generator's output was rendered with the real Mermaid library in headless Chromium:

| Syntax | Verified with | Notes |
|---|---|---|
| `extended` (default) | Mermaid 11.3.0, 11.12.0, 12.1.0 | ISO outlines for almost every symbol (stadium, diamond, framed rectangle, document, horizontal cylinder, loop limit, …). |
| `classic` | Mermaid 10.4.0, 10.9.1, 11.x, 12.1.0 | Bracket shapes; approximated symbols carry `iso_*` classes. Mermaid 9.4–10.3 work when edge labels are plain ASCII. |

Known approximations are listed in every `generate_mermaid` result (`fidelity_notes`) and in
Part 3 of the guide. Generated code parses back into the same model (tested), so charts can
round-trip through `validate_mermaid`.

### Protocol and transports

- MCP revisions 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 (initialize handshake).
  Clients that first probe the 2026-07-28 `server/discover` method get "method not found"
  and fall back to the handshake; the official Python SDK does this automatically (tested).
- **stdio**: newline-delimited JSON-RPC; stdout carries only protocol messages, logs go to
  stderr.
- **Streamable HTTP**: `POST /mcp` returns `application/json` (202 for notifications); `GET`
  and `DELETE` return 405 (no server-initiated stream, stateless); `GET /healthz` for health
  checks. Binds to `127.0.0.1` by default, rejects browser origins other than localhost and
  `--allow-origin` values (DNS-rebinding protection), and supports `--auth-token` (or
  `ISO5807_MCP_TOKEN`) for `Authorization: Bearer` checks.

## Development

```bash
python3 -m unittest discover -s tests -v
```

The suite covers the rule engine, analyser, Mermaid round-trips, the JSON-RPC layer, stdio
and HTTP transports, the CLI, consistency between code, guide, examples and configuration,
and (when the `mcp` Python SDK ≥ 2 is installed) interoperability with the official client.

## About the standard

ISO 5807:1985 is published by ISO and was adopted in the US as ANSI/ISO 5807-1985
(superseding ANSI X3.5-1970). This repository paraphrases its provisions and does not
reproduce the standard's text; rules marked *Practice* go beyond the standard and are
labelled as such. For the authoritative text, obtain the standard from ISO or your national
standards body.
