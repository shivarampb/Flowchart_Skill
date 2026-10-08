---
name: iso5807-flowchart
description: Design, review, validate or convert flowcharts that must conform to ANSI/ISO 5807:1985 (program, data and system flowcharts, Mermaid flowcharts). Use whenever the user asks for a flowchart, process flow, algorithm diagram or decision flow, or wants one reviewed or converted from text, pseudocode, BPMN or Mermaid.
argument-hint: "[process description | Mermaid code | path to flowchart JSON]"
allowed-tools: mcp__iso5807-flowchart__*
---

# ISO 5807 flowchart workflow

Input: $ARGUMENTS

Decide the mode from the input:

- **Design**: a process description, pseudocode or BPMN/UML diagram.
- **Review**: Mermaid code (`flowchart ...` / `graph ...`) or a flowchart JSON file.

## Design mode

1. **Frame**: choose the chart type. A program flowchart describes what a program does; use
   a system flowchart when people, documents or several systems take part. Choose the
   abstraction level from the audience. Name the trigger (start Terminator) and every
   outcome (end Terminators, including failure outcomes).
2. **Extract**: list steps as verb + object at one level of abstraction. Turn every
   fallible or conditional verb (*check, verify, approve, find, try, if, unless, until*)
   into a Decision with a testable, quantified question and complementary labelled exits.
   Add an `Otherwise` exit to multi-way Decisions.
3. **Close**: give every loop an exit and a bound (counter or timeout), every fallible
   operation an outcome Decision, and every path an end.
4. **Model** the chart as JSON and call `validate_flowchart`. Repeat until there are no
   errors. Fix warnings or state why one stays.
5. **Analyze** with `analyze_flowchart` and act on `failure_state`, `loop` and `granularity`
   insights. Mention relevant `bottleneck` insights to the user.
6. **Render** with `generate_mermaid`. Use `syntax: "classic"` only if the user's renderer
   predates Mermaid 11.3.

## Review mode

1. Run `validate_mermaid` (Mermaid input) or `validate_flowchart` (JSON input), then
   `analyze_flowchart` on the resulting model.
2. Report findings grouped as **errors**, **warnings** and **logic insights**. For each,
   give the symbol id, the rule ID and the concrete fix.
3. Produce the corrected chart, validate it, and render it with `generate_mermaid`.

## Answer format

1. The Mermaid code block.
2. **Assumptions**: short bullets (scope, thresholds, actors you inferred).
3. **Conformance**: `ISO 5807 validation: N errors, M warnings`, listing any remaining
   warning with its rule ID and the reason it stays.
4. **Logic notes**: at most five bullets from the analysis (loops, bottlenecks, failure
   paths).

Look up a symbol with `iso5807_symbol_reference` and a rule with `iso5807_rules` instead of
guessing. The full guide is the resource `iso5807://guide`.
