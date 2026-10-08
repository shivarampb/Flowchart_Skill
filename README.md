# ANSI/ISO 5807:1985 Flowchart Skill

A Claude Code skill for drawing, reviewing and converting flowcharts that conform to the
ANSI/ISO 5807:1985 flowchart standard. It bundles a strict guide to the standard, an analysis
of the flowcharting skill, and an engine (CLI and MCP server, Python standard library only)
that validates charts, analyses their logic and renders them as Mermaid.

| Path | What it is |
|---|---|
| [`SKILL.md`](SKILL.md) | The skill: workflow, rules and answer format Claude follows. |
| [`docs/ANSI-ISO-5807-Flowchart-Guide.md`](docs/ANSI-ISO-5807-Flowchart-Guide.md) | Part 1: rules and syntax (symbols, flowlines, connectors, text, structure). Part 2: analysis of the skill (abstraction, systemic thinking, granularity, communication). |
| [`mcp_server/`](mcp_server/) | The engine: `check`/`validate`/`analyze`/`mermaid` CLI and an MCP server. Python ≥ 3.9, no installs. |
| [`examples/`](examples/) | Sample flowcharts, valid and deliberately flawed. |
| [`integrations/`](integrations/) | Optional MCP registration for Claude Code, Claude Desktop config, claude.ai Project instructions. |
| [`tests/`](tests/) | Unit, protocol, transport, layout and SDK-interoperability tests. |

## Install as a Claude Code skill (VS Code, terminal, desktop app)

The repository **is** the skill folder (`SKILL.md` sits at its top). Put it in your project
under `.claude/skills/flowchart_rules/`:

```text
your-project/
└── .claude/
    └── skills/
        └── flowchart_rules/          <- this repository
            ├── SKILL.md
            ├── docs/
            ├── examples/
            └── mcp_server/
```

```bash
cd your-project
git clone https://github.com/shivarampb/Flowchart_Skill.git .claude/skills/flowchart_rules
```

Copying the folder works just as well. To have the skill in every project, put it in
`~/.claude/skills/flowchart_rules/` instead.

**Requirements:** Python 3.9 or newer on the `PATH` (`python3`, or `python` on Windows).
Nothing else.

**Use it.** In the Claude Code panel in VS Code (or the terminal), type
`/flowchart_rules <process description, Mermaid code or file path>`, or simply ask for a
flowchart; the skill loads automatically. Claude then:

1. models the chart as JSON in `flowcharts/<name>.json`;
2. runs the bundled checker, which is pre-approved while the skill runs:
   `python3 .claude/skills/flowchart_rules/mcp_server/server.py check flowcharts/<name>.json --out flowcharts/<name>.mmd`;
3. fixes every error the checker reports, then answers with the Mermaid diagram,
   its assumptions, the conformance line and logic notes.

**Viewing the diagrams in VS Code.** Open the `.mmd` file or the answer's Mermaid block with
a Mermaid preview extension. The default output uses Mermaid 11.3+ shapes (`@{ shape: … }`);
if your previewer reports a syntax error there, it bundles an older Mermaid. Ask for the
*classic* syntax (CLI `--classic`), which works from Mermaid 10.4.

**Notes**

- The `/` command name comes from `name:` in `SKILL.md` (`flowchart_rules`). If you rename the
  folder, change that field too, and the path in the MCP template below if you use it.
- If `/flowchart_rules` does not show up, start a new Claude Code session.
- The pre-approval covers the turn in which the skill runs. If Claude re-runs the checker in
  a later message, Claude Code asks first; answer "Yes, don't ask again" to keep it approved.

### Optional: the MCP tools

The skill works through the CLI alone. If you also want the tools as native MCP tools
(`validate_flowchart`, `analyze_flowchart`, `generate_mermaid`, `validate_mermaid`, …):

- **Project install:** copy
  [`integrations/claude-code/project.mcp.json`](integrations/claude-code/project.mcp.json)
  to `your-project/.mcp.json` (merge it if the file exists) and merge
  [`integrations/claude-code/project-settings.json`](integrations/claude-code/project-settings.json)
  into `your-project/.claude/settings.json`. Approve the server when Claude Code asks;
  `/mcp` shows its status.
- **Personal install** (`~/.claude/skills/flowchart_rules`):
  `claude mcp add --scope user iso5807-flowchart -- python3 ~/.claude/skills/flowchart_rules/mcp_server/server.py`

On Windows, use `python` instead of `python3` in these commands.

## Other clients

### Claude Desktop

Add the server to `claude_desktop_config.json` (Settings → Developer → Edit Config) with the
absolute path of the skill folder, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "iso5807-flowchart": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/flowchart_rules/mcp_server/server.py"]
    }
  }
}
```

On Windows use `"command": "python"` and a path such as
`"C:\\Users\\you\\project\\.claude\\skills\\flowchart_rules\\mcp_server\\server.py"`.

### claude.ai Projects

1. Paste [`integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md`](integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md)
   into the Project's **Instructions**.
2. Upload `docs/ANSI-ISO-5807-Flowchart-Guide.md` as **project knowledge**.
3. Optional, for the tools: claude.ai connects only to remote MCP servers, so run the server
   over HTTP behind HTTPS and add it as a custom connector (**Settings → Connectors → Add
   custom connector**, URL `https://<your-host>/<path>`):

   ```bash
   python3 mcp_server/server.py --http --host 0.0.0.0 --port 8765 --path /mcp-<random-string>
   ```

   The endpoint must be publicly reachable over HTTPS (reverse proxy or tunnel). Custom
   connectors use OAuth or no authentication, so `--auth-token` cannot be used there; an
   unguessable `--path` keeps casual callers out. The tools are read-only and access no data.

### Any other MCP client

```bash
python3 mcp_server/server.py                      # stdio (default)
python3 mcp_server/server.py --http --port 8765   # Streamable HTTP at http://127.0.0.1:8765/mcp
npx @modelcontextprotocol/inspector python3 mcp_server/server.py   # interactive inspection
```

`pip install ./mcp_server` also installs the engine as the `iso5807-mcp` command.

## Command line

Run from the skill folder (or give the full path to `mcp_server/server.py`):

```bash
python3 mcp_server/server.py check examples/refund-request.json            # one-stop report
python3 mcp_server/server.py check examples/informal-approval.mmd --classic --out out.mmd
python3 mcp_server/server.py validate examples/order-processing.json      # JSON reports
python3 mcp_server/server.py analyze  examples/refund-request.json
python3 mcp_server/server.py mermaid  examples/monthly-billing.json [--classic] [--out FILE.mmd]
python3 mcp_server/server.py check-mermaid examples/informal-approval.mmd
```

`check` accepts a flowchart JSON model or Mermaid code and prints the findings (rule ID,
symbols, fix), the logic analysis and the Mermaid code; `--json` prints everything as JSON.
Use `-` instead of a file name to read standard input. Exit codes: 0 conformant, 1 errors
found, 2 unreadable input. `--out` writes only `.mmd`/`.mermaid` files.

## The engine

### MCP tools

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

### Flowchart model

See the example in [`SKILL.md`](SKILL.md#json-model). Fields:

| Field | Values |
|---|---|
| `chart_type` | `program` (default), `data`, `system`, `program_network`, `system_resources` |
| `direction` | `TB` (default) or `LR`; `BT`/`RL` are reported (FLW-01) |
| node `type` | `terminator`, `process`, `predefined_process`, `manual_operation`, `preparation`, `decision`, `parallel_mode`, `loop_limit`, `data`, `stored_data`, `internal_storage`, `sequential_access_storage`, `direct_access_storage`, `document`, `manual_input`, `card`, `punched_tape`, `display`, `connector`, `annotation`, `ellipsis`; legacy `off_page_connector`. Common aliases (`start`, `io`, `diamond`, `subroutine`, …) are accepted. |
| node extras | `role` + `loop_id` (loop limits), `annotates` (annotations), `detail_ref` (striped symbol), `multiple` (stacked data symbols), `off_page` (cross-page connector), `page` |
| edge `kind` | `flow` (default), `dashed`, `communication_link`, `control_transfer` |

The full JSON schema is the resource `iso5807://schema/flowchart` and part of each tool's
input schema.

### Mermaid support

The generator's output was rendered with the real Mermaid library in headless Chromium:

| Syntax | Verified with | Notes |
|---|---|---|
| `extended` (default) | Mermaid 11.3.0, 11.12.0, 12.1.0 | ISO outlines for almost every symbol (stadium, diamond, framed rectangle, document, horizontal cylinder, loop limit, …). |
| `classic` | Mermaid 10.4.0, 10.9.1, 11.x, 12.1.0 | Bracket shapes; approximated symbols carry `iso_*` classes. Mermaid 9.4–10.3 work when edge labels are plain ASCII. |

Known approximations are listed in every result (`fidelity_notes`) and in Part 3 of the
guide. Generated code parses back into the same model, so charts round-trip.

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
and HTTP transports, the CLI, the skill layout (the package copied to
`<project>/.claude/skills/flowchart_rules/`), consistency between code, guide, examples and
configuration, and (when the `mcp` Python SDK ≥ 2 is installed) interoperability with the
official client.

- Rules live in `mcp_server/iso5807_mcp/knowledge.py`; every rule ID must appear in the
  guide (a test enforces it).
- The worked example in the guide is generated: after changing the generator or the
  `refund-request` example, run `python3 mcp_server/server.py mermaid
  examples/refund-request.json` and paste the output between the `BEGIN/END GENERATED`
  markers.
- Keep stdout clean in `transport.py`: in stdio mode it carries the protocol.
- Do not add a `CLAUDE.md` or a `.claude/` folder to this package: inside
  `.claude/skills/flowchart_rules/` Claude Code would load them as extra instructions or a
  second skill.

## About the standard

ISO 5807:1985 is published by ISO and was adopted in the US as ANSI/ISO 5807-1985
(superseding ANSI X3.5-1970). This repository paraphrases its provisions and does not
reproduce the standard's text; rules marked *Practice* go beyond the standard and are
labelled as such. For the authoritative text, obtain the standard from ISO or your national
standards body.
