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
`check-mermaid` print JSON. `rules` lists every rule and `rules CON-02` explains one.

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

## Complete rule index

Every rule the checker knows. Each entry gives the basis (ISO = the standard, Practice =
professional practice beyond it, Schema = the JSON model), the default severity, and how the
rule is enforced: **checked** means the `check` report flags violations; **analysis** means
it appears as a logic insight; **judgment** means no tool can see it in a JSON model, so you
apply it yourself. The generated Mermaid already satisfies three judgment rules: arrowheads
on every line (FLW-02), horizontal text (TXT-02) and right-angle flowlines (FLW-05; Mermaid
11.3 ignores that setting and draws curves).

<!-- BEGIN RULE INDEX (generated by: server.py rules) -->
**Core symbols: choice, geometry and meaning**

- `SYM-01` Use only standard symbols, with their defined meaning (ISO, error, checked)
- `SYM-02` Basic symbols by default, specific symbols when the medium or nature matters (ISO, info, judgment): The basic symbols (Process, Data, Stored data, Line) may always be used. Use a specific symbol (Document, Manual operation, Direct access storage, ...) only when the medium or the nature of the function is known and relevant.
- `SYM-03` Shape carries meaning; size, colour and shading do not (ISO, info, judgment): Symbols may be drawn in any size, but their shape must stay recognisable and their proportions consistent within a chart. Do not rotate or mirror symbols. Colour, shading and line weight carry no meaning in the standard.
- `SYM-04` A striped symbol points to a detailed representation (ISO, error, checked)
- `SYM-05` Predefined process names a function specified elsewhere (ISO, info, judgment): Use the Predefined process for a named process (subroutine, module, library function) whose steps are specified elsewhere; use a striped symbol when the detail is in the same documentation set.
- `SYM-06` Use symbols appropriate to the chart type (ISO, warning, checked)
- `SYM-07` Multiple-symbol convention applies to data symbols (ISO, warning, checked)
- `SYM-08` A Terminator is either a start or an end (ISO, error, checked)
- `SYM-09` A Decision has one entry and two or more exits (ISO, error, checked)
- `SYM-10` Parallel mode synchronizes two or more paths (ISO, warning, checked)
- `SYM-11` Loop limits come in matched pairs with one identifier (ISO, error, checked)
- `SYM-12` Ellipsis shows omitted symbols (ISO, info, checked)

**Flowlines: direction, arrowheads, crossings, junctions, line types**

- `FLW-01` Normal flow direction is top-to-bottom and left-to-right (ISO, warning, checked)
- `FLW-02` Arrowheads are mandatory against the normal direction (ISO, warning, judgment): Every flowline whose direction is not the normal one (upward or right-to-left, e.g. a loop back-edge) carries an arrowhead. Arrowheads may be used on any line for clarity; in program flowcharts put them on all flowlines.
- `FLW-03` Crossing lines have no logical relationship (ISO, info, judgment): Two flowlines that cross do not join and have no logical relationship. Keep crossings to a minimum by moving symbols or using connectors.
- `FLW-04` Junctions merge incoming lines into one outgoing line (ISO, info, judgment): Two or more incoming flowlines may join into a single outgoing flowline. Draw joins as offset T-junctions with the arrowhead showing the merged direction; never make a four-way join that looks like a crossing.
- `FLW-05` Route lines orthogonally and consistently (Practice, info, judgment): Draw flowlines as horizontal and vertical segments. Enter symbols at the top (or left) and leave at the bottom (or right); Decision exits leave from the vertices.
- `FLW-06` Only Decisions (and Parallel mode) branch (Practice, error, checked)
- `FLW-07` A flowline connects two different symbols (Practice, error, checked)
- `FLW-08` Line variants keep their defined meaning (ISO, warning, checked)
- `FLW-09` No redundant parallel flowlines (Practice, warning, checked)

**Connectors: on-page and cross-page continuation**

- `CON-01` A connector breaks a line: it is an exit or an entry, never both (ISO, error, checked)
- `CON-02` Matching connectors carry the same unique identifier (ISO, error, checked)
- `CON-03` Keep connector identifiers short and systematic (Practice, warning, checked)
- `CON-04` Off-page connector is an ANSI X3.5 legacy symbol (ISO, warning, checked)
- `CON-05` Connectors must not hide structure (Practice, info, judgment): Use connectors to avoid long or crossing lines and to continue across pages. Never use them to jump into the middle of a loop or decision structure, and prefer a direct line when it is short and uncluttered.

**Text, labels and annotation**

- `TXT-01` Minimum text inside symbols (ISO, warning, checked)
- `TXT-02` Text reads left-to-right and top-to-bottom (ISO, info, judgment): Text inside and beside symbols is written to be read from left to right and top to bottom, whatever the direction of flow.
- `TXT-03` Label every Decision exit with its outcome (ISO, error, checked)
- `TXT-04` Place symbol identifiers and descriptions outside the symbol (ISO, info, judgment): A symbol identifier (for cross-reference with other documentation) is placed outside the symbol near its top, consistently on the same side throughout the chart; a symbol description may be placed beside it. A striped symbol's reference goes inside the stripe.
- `TXT-05` Process text is an imperative action (Practice, warning, checked)
- `TXT-06` Decision text is a testable condition (Practice, info, checked)
- `TXT-07` Every symbol carries text (Practice, warning, checked)
- `TXT-08` Annotations attach with a dashed line and never carry flow (ISO, error, checked)
- `TXT-09` Use consistent vocabulary (Practice, info, judgment): Use one term per concept across the chart and its documentation set, and define abbreviations in a legend or Annotation.

**Logical integrity of the flow (entries, exits, loops, outcomes)**

- `STR-01` Flow begins and ends at boundary symbols (Practice, error, checked)
- `STR-02` Single entry per program flowchart (Practice, warning, checked)
- `STR-03` Every symbol is reachable (Practice, error, checked)
- `STR-04` Every path can terminate (Practice, error, checked)
- `STR-05` Every loop has an exit condition (Practice, error, checked)
- `STR-06` Decision outcomes are complete (Practice, warning, checked)
- `STR-07` No redundant Decisions (Practice, warning, checked)
- `STR-08` Model failure states (Practice, info, analysis)
- `STR-09` Data flowcharts alternate data and processing (ISO, warning, checked)

**Layout, density and granularity**

- `LAY-01` Limit symbols per page (Practice, warning, checked)
- `LAY-02` Keep one level of abstraction per chart (Practice, info, analysis)
- `LAY-03` Factor out repeated logic (Practice, info, analysis)
- `LAY-04` Align and space symbols uniformly (Practice, info, judgment): Draw symbols of one type at one size, aligned on a grid with even spacing; the main path runs straight, alternatives branch to one side and rejoin below.
- `LAY-05` Identify the chart (Practice, info, checked)

**Integrity of the JSON flowchart model used by the tools**

- `MOD-01` Symbol ids are unique and non-empty (Schema, error, checked)
- `MOD-02` References point to existing symbols (Schema, error, checked)
- `MOD-03` The model is well-formed (Schema, error, checked)
<!-- END RULE INDEX -->

## Reference

- Full rule book with rationale and the analysis of the flowcharting skill:
  `${CLAUDE_SKILL_DIR}/docs/ANSI-ISO-5807-Flowchart-Guide.md`. It is long: search it for a
  rule ID such as `CON-02` and read only that section.
- Worked examples (valid and deliberately flawed): `${CLAUDE_SKILL_DIR}/examples/`.
