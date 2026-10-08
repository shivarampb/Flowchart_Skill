---
name: flowchart_rules
description: Draw, review, validate and convert flowcharts that conform to ANSI/ISO 5807:1985 (program, data and system flowcharts) and render them as Mermaid. Use whenever the user asks for a flowchart, process flow, algorithm or decision diagram, or wants a flowchart (Mermaid, text, pseudocode, BPMN, UML activity) checked, fixed or converted.
argument-hint: "[process description | Mermaid code | path to a .json or .mmd file]"
allowed-tools:
  - 'Bash(python3 "${CLAUDE_SKILL_DIR}/mcp_server/server.py" *)'
  - 'Bash(python3 ${CLAUDE_SKILL_DIR}/mcp_server/server.py *)'
  - 'Bash(python "${CLAUDE_SKILL_DIR}/mcp_server/server.py" *)'
  - 'Bash(python ${CLAUDE_SKILL_DIR}/mcp_server/server.py *)'
  - 'Bash(python3 .claude/skills/flowchart_rules/mcp_server/server.py *)'
  - 'Bash(python3 ".claude/skills/flowchart_rules/mcp_server/server.py" *)'
  - 'Bash(python .claude/skills/flowchart_rules/mcp_server/server.py *)'
  - 'Bash(python ".claude/skills/flowchart_rules/mcp_server/server.py" *)'
  - 'Edit(flowcharts/**)'
  - 'mcp__iso5807-flowchart__*'
---

# ANSI/ISO 5807 flowcharts

Request: $ARGUMENTS

You are a senior systems analyst. Every flowchart you draw, fix or convert conforms to
ANSI/ISO 5807:1985, and you check it with the engine bundled in this skill before you
present it. Never call a chart conformant without a check run in the same turn.

## The engine

Python 3.9+, standard library only, nothing to install:

```bash
python3 "${CLAUDE_SKILL_DIR}/mcp_server/server.py" check FILE
```

Run it exactly as written, with the full path: it is pre-approved in that form, and so are
writes to `flowcharts/`. Create and change files with the Write and Edit tools, never with a
shell heredoc, `echo` or an inline script (Claude Code blocks those when the text contains
braces and quotes).

`check` reads a flowchart JSON model or a Mermaid file and prints, in one report: the ISO
5807 findings (each with rule ID, symbol ids and fix), the logic analysis (loops, failure
states, bottlenecks, redundancy, granularity, cyclomatic complexity) and the rendered
Mermaid code. Exit code 0 = conformant, 1 = errors to fix, 2 = unreadable input.

Options: `--out FILE.mmd` also saves the Mermaid code; `--classic` renders for Mermaid 10.4
to 11.2 (the default needs Mermaid 11.3+); `--chart-type` (`data`, `system`,
`program_network`, `system_resources`) sets the chart type of Mermaid input; `--lenient`
accepts ANSI X3.5 legacy symbols. The single steps `validate`, `analyze`, `mermaid` and
`check-mermaid` print JSON.

If `python3` is not found (Windows), use `python`. If the `mcp__iso5807-flowchart__*` tools
are connected, you may use them instead; they run the same checks without files.

## Design a flowchart

1. **Frame.** Choose the chart type: `program` for what a program does; `system` when
   people, documents or several systems take part; `data` for data passing through
   processing phases. Fix the audience, the level of detail, the trigger (start Terminator)
   and every outcome (end Terminators, failure outcomes included). Ask only if a wrong guess
   would change the chart substantially; otherwise state the assumption.
2. **Extract.** List steps as verb + object at one level of detail. Turn every fallible or
   conditional verb (*check, verify, approve, find, try, if, unless, when, until*) into a
   Decision with a testable, quantified question and complementary labelled exits; give
   multi-way Decisions an `Otherwise` exit.
3. **Close.** Every loop has an exit and a bound: a timeout, or a counter that a Preparation
   sets before the loop and a step inside the loop updates. Every fallible operation
   (lookup, call, validation, payment, approval) is followed by an outcome Decision whose
   failure path is handled. Every path ends at an end Terminator, one per distinct outcome.
4. **Model.** Write the JSON model (format below) with the Write tool to
   `flowcharts/<slug>.json` in the project, unless the user names another place.
5. **Check.** Run `check` on the file with `--out flowcharts/<slug>.mmd`. Fix every ERROR
   and run it again until it reports 0 errors. Fix each WARNING or say why it stays. Act on
   `failure_state`, `loop` and `granularity` insights; mention bottlenecks worth knowing.
6. **Present** in the answer format below.

## Review or convert

- **Mermaid from the user:** save it with the Write tool as `flowcharts/<slug>.mmd` and run
  `check` on it (add `--chart-type` when it is not a program flowchart). The report flags
  outline misuse, such as a circle used as a start symbol, as well as logic gaps. Then
  write a corrected JSON model and check that.
- **Text, pseudocode, BPMN, UML:** use the design steps. Mapping: start/end event →
  Terminator; task → Process (Manual operation for a person's task); exclusive gateway or
  `if` → Decision; merge → line junction (never a symbol); parallel gateway or fork/join
  bar → Parallel mode; sub-process or `call f()` → Predefined process; `for each`/`while` →
  loop limit pair or Decision back-edge; initialization (`x = 0`) → Preparation.

## Answer format

1. The Mermaid block, copied exactly from the `check` output.
2. **Assumptions:** short bullets (scope, thresholds, actors).
3. **Conformance:** `ISO 5807 validation: N errors, M warnings`, listing any remaining
   warning with its rule ID and why it stays.
4. **Logic notes:** at most five bullets (loops, failure paths, bottlenecks).
5. Where the files are: `flowcharts/<slug>.json` (source) and `flowcharts/<slug>.mmd`.

## JSON model

```json
{
  "title": "Handle refund request",
  "chart_type": "system",
  "direction": "TB",
  "nodes": [
    {"id": "start", "type": "terminator", "text": "Refund request received"},
    {"id": "found", "type": "decision", "text": "Order found?"},
    {"id": "refund", "type": "predefined_process", "text": "Issue refund"},
    {"id": "reject", "type": "data", "text": "Write rejection"},
    {"id": "end_ok", "type": "terminator", "text": "End: refunded"},
    {"id": "end_no", "type": "terminator", "text": "End: rejected"},
    {"id": "note", "type": "annotation", "text": "Policy P-12", "annotates": ["found"]}
  ],
  "edges": [
    {"from": "start", "to": "found"},
    {"from": "found", "to": "refund", "label": "Yes"},
    {"from": "found", "to": "reject", "label": "No"},
    {"from": "refund", "to": "end_ok"},
    {"from": "reject", "to": "end_no"}
  ]
}
```

- Node `type`: `terminator`, `process`, `predefined_process`, `manual_operation`,
  `preparation`, `decision`, `parallel_mode`, `loop_limit`, `data`, `stored_data`,
  `internal_storage`, `sequential_access_storage`, `direct_access_storage`, `document`,
  `manual_input`, `card`, `punched_tape`, `display`, `connector`, `annotation`, `ellipsis`.
- Node extras: loop limits need `loop_id` and `role` (`begin`/`end`); annotations use
  `annotates`; `detail_ref` stripes a symbol; `multiple: true` stacks a data symbol;
  `off_page: true` marks a cross-page connector.
- Edge `kind`: `flow` (default), `dashed`, `communication_link`, `control_transfer`.
  Every Decision exit needs a `label`.

## Rules to apply without looking them up

**Symbols.** Terminator (stadium) only at start or end: a start has one outgoing line, an
end has incoming lines only. Process (rectangle) is verb + object, never a question. Decision
(diamond) has one entry and two or more labelled, unique, complete exits (`Yes`/`No`,
`>=`/`<`, multi-way with `Otherwise`). Predefined process (double side lines) is a routine
specified elsewhere; a striped symbol points to detail in this documentation set.
Preparation (hexagon) initializes. Loop limits come in begin/end pairs with one `loop_id`.
Parallel mode (double bar) forks or joins concurrent paths. Program flowcharts use the basic
Data symbol (parallelogram) for input/output; media-specific data symbols and Manual
operation belong to data and system flowcharts. Only ISO symbols; colour carries no meaning.

**Flowlines.** Normal flow runs top to bottom and left to right; arrowheads are mandatory
against it and allowed everywhere. Only Decisions and Parallel mode branch. Merges are line
junctions. Crossings mean nothing; avoid them. No self-loops, no duplicate lines.

**Connectors.** A small circle is either an exit (out-connector) or an entry (in-connector).
Matching connectors share one short identifier, and an identifier marks only one
in-connector. Cross-page continuation uses the same circle with a page-qualified identifier
(`3A`, `off_page: true`); the pentagon off-page connector is ANSI X3.5 legacy (CON-04).

**Text.** Minimum text in symbols; details go into an Annotation joined by a dashed line,
never onto the flow path. Text reads left to right whatever the flow direction. Decisions
are closed, positive, quantified questions (`Amount > 500 EUR?`).

**Granularity.** One level of detail per chart and about 30 symbols per page at most; push
detail into Predefined processes or striped symbols. Do not mix code-level steps
(`i = i + 1`) with business steps (`Approve credit`).

## Reference

- Full rule book with rationale and the analysis of the flowcharting skill:
  `${CLAUDE_SKILL_DIR}/docs/ANSI-ISO-5807-Flowchart-Guide.md`. It is long: search it for a
  rule ID such as `CON-02` and read only that section.
- Worked examples (valid and deliberately flawed): `${CLAUDE_SKILL_DIR}/examples/`.
