"""ANSI/ISO 5807:1985 knowledge base: symbols, chart types and rules.

The descriptions paraphrase the standard; its text is copyrighted and is not
reproduced here. Every rule records its ``basis``:

* ``ISO 5807``  - paraphrase of a provision of ISO 5807:1985 (adopted in the
  USA as ANSI/ISO 5807-1985, which replaced ANSI X3.5-1970).
* ``ANSI X3.5`` - legacy ANSI X3.5-1970 convention, kept for compatibility.
* ``Practice``  - widely adopted professional practice that goes beyond the
  letter of the standard (structured-flow integrity, readability, layout).
* ``Schema``    - integrity rule of this server's JSON flowchart model.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple

STANDARD = "ANSI/ISO 5807:1985"
STANDARD_TITLE = (
    "Information processing - Documentation symbols and conventions for data, "
    "program and system flowcharts, program network charts and system resources charts"
)

SEVERITIES = ("error", "warning", "info")

# ---------------------------------------------------------------------------
# Chart types (ISO 5807 defines five kinds of chart)
# ---------------------------------------------------------------------------

CHART_TYPES: Dict[str, Dict[str, str]] = {
    "program": {
        "name": "Program flowchart",
        "purpose": "Sequence of operations in a program.",
        "composition": (
            "Process symbols for the operations and for the logical path to follow, "
            "line symbols for the control flow, and special symbols that make the chart "
            "easier to write and read. Input/output steps are commonly drawn with the "
            "basic Data symbol."
        ),
        "validation": (
            "Full control-flow integrity: start/end Terminators, single exits except at "
            "Decisions, labelled and complete Decision outcomes, reachability, loop exits."
        ),
    },
    "data": {
        "name": "Data flowchart",
        "purpose": (
            "Path of data in the solution of a problem: the major processing phases and "
            "the data media used."
        ),
        "composition": (
            "Data symbols (which may show the medium), process symbols, flowlines for the "
            "flow of data, and special symbols. Each processing symbol has data on its "
            "input and output sides; the chart begins and ends with data symbols (or "
            "special symbols)."
        ),
        "validation": "Data/process alternation, connector pairing, decision labelling, "
                      "reachability.",
    },
    "system": {
        "name": "System flowchart",
        "purpose": "Control of operations and the flow of data in a system.",
        "composition": (
            "Data symbols showing the existence of data (and possibly the medium), process "
            "symbols, flowlines for data flow and for control flow between processes, and "
            "special symbols."
        ),
        "validation": "Connector pairing, decision labelling, reachability, loop exits.",
    },
    "program_network": {
        "name": "Program network chart",
        "purpose": (
            "Path of program activations and their interactions with related data. Each "
            "program appears only once."
        ),
        "composition": (
            "Process symbols (one per program), data symbols, lines for activations and "
            "data flow, and special symbols."
        ),
        "validation": "Symbol, text and connector rules only (no control-flow logic).",
    },
    "system_resources": {
        "name": "System resources chart",
        "purpose": (
            "Configuration of data units and processing units appropriate to a problem or "
            "a set of problems."
        ),
        "composition": (
            "Data symbols for input, output and storage devices, process symbols for "
            "processors, lines for data transfer and control transfer, and special symbols."
        ),
        "validation": "Symbol, text and connector rules only (no control-flow logic).",
    },
}

CHART_TYPE_ALIASES = {
    "program_flowchart": "program",
    "programflowchart": "program",
    "flowchart": "program",
    "algorithm": "program",
    "data_flowchart": "data",
    "data_flow": "data",
    "dataflow": "data",
    "system_flowchart": "system",
    "systems": "system",
    "network": "program_network",
    "program_network_chart": "program_network",
    "resources": "system_resources",
    "system_resources_chart": "system_resources",
}

# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------

PROCESS_FAMILY = (
    "process",
    "predefined_process",
    "manual_operation",
    "preparation",
    "decision",
    "parallel_mode",
    "loop_limit",
)
DATA_FAMILY = (
    "data",
    "stored_data",
    "internal_storage",
    "sequential_access_storage",
    "direct_access_storage",
    "document",
    "manual_input",
    "card",
    "punched_tape",
    "display",
)
SPECIAL_FAMILY = ("terminator", "connector", "annotation", "ellipsis")
EXTENSION_TYPES = ("off_page_connector",)  # ANSI X3.5-1970 legacy, not in ISO 5807
CONNECTOR_TYPES = ("connector", "off_page_connector")
NODE_TYPES = PROCESS_FAMILY + DATA_FAMILY + SPECIAL_FAMILY + EXTENSION_TYPES

EDGE_KINDS = ("flow", "dashed", "communication_link", "control_transfer")

# Specific data symbols and manual symbols belong to data/system flowcharts.
PROGRAM_CHART_DISCOURAGED = (
    "manual_operation",
    "stored_data",
    "internal_storage",
    "sequential_access_storage",
    "direct_access_storage",
    "document",
    "manual_input",
    "card",
    "punched_tape",
    "display",
)
STRUCTURE_CHART_DISCOURAGED = ("decision", "loop_limit")  # program network / system resources


def _symbol(
    sid: str,
    name: str,
    family: str,
    level: str,
    geometry: str,
    meaning: str,
    use_when: List[str],
    do_not: List[str],
    text: str,
    flow: str,
    mermaid_extended: str,
    mermaid_classic: str,
    fidelity: str = "exact",
    note: str = "",
    standard: str = "ISO 5807",
    model: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    entry: Dict[str, object] = {
        "id": sid,
        "name": name,
        "family": family,
        "level": level,
        "standard": standard,
        "geometry": geometry,
        "meaning": meaning,
        "use_when": use_when,
        "do_not": do_not,
        "text_convention": text,
        "flow_convention": flow,
        "mermaid": {
            "extended_shape": mermaid_extended,
            "classic_syntax": mermaid_classic,
            "fidelity": fidelity,
        },
        "model": model or {"node_type": sid},
    }
    if note:
        entry["mermaid"]["note"] = note  # type: ignore[index]
    return entry


SYMBOLS: List[Dict[str, object]] = [
    # ----------------------------------------------------------- process family
    _symbol(
        "process", "Process", "process", "basic",
        "Rectangle, normally wider than it is high.",
        "Any processing function: an operation or group of operations that changes the "
        "value, form or location of information. It is the basic process symbol and may "
        "be used whenever no specific process symbol applies.",
        ["A single, well-defined action performed by the system.",
         "A step whose specific nature (manual, predefined, preparation) does not matter."],
        ["Put a question in it - conditions belong in a Decision.",
         "Give it more than one outgoing flowline in a program flowchart.",
         "Combine several unrelated actions in one box."],
        "Imperative verb + object, e.g. 'Calculate invoice total'.",
        "One entry (incoming lines may join before it) and exactly one exit.",
        "rect", "id[text]",
    ),
    _symbol(
        "predefined_process", "Predefined process", "process", "specific",
        "Rectangle with an additional vertical line just inside each of the left and "
        "right sides (double side lines).",
        "A named process consisting of one or more operations or program steps that are "
        "specified elsewhere, e.g. a subroutine, module or library function.",
        ["Calling a subroutine, module or reusable procedure.",
         "Collapsing a detailed sub-flow to keep one level of abstraction."],
        ["Use it for a step that is not specified anywhere else.",
         "Stripe it as well - the double lines already say 'detailed elsewhere'."],
        "Name of the routine or module, e.g. 'Compute shipping cost'.",
        "One entry and exactly one exit.",
        "fr-rect", "id[[text]]",
    ),
    _symbol(
        "manual_operation", "Manual operation", "process", "specific",
        "Trapezoid with the longer of its parallel sides at the top.",
        "Any process performed by a human being.",
        ["A step executed by a person without automatic support (inspect, sign, sort, "
         "approve on paper)."],
        ["Use it for keyboard entry at processing time - that is Manual input.",
         "Use it in program flowcharts, which describe what the program does."],
        "Imperative verb + object, naming who acts if relevant: 'Clerk checks signature'.",
        "One entry and exactly one exit.",
        "trap-t", "id[\\text/]",
    ),
    _symbol(
        "preparation", "Preparation", "process", "specific",
        "Hexagon elongated horizontally (rectangle with pointed left and right ends).",
        "Modification of an instruction or group of instructions to affect later activity, "
        "e.g. setting a switch, modifying an index register or initializing a routine.",
        ["Initializing counters, accumulators, switches or loop control variables.",
         "Setting up a routine before it is used."],
        ["Use it for ordinary data processing.",
         "Use it as a decision - it has a single exit."],
        "The initialization performed, e.g. 'Set i = 1, total = 0'.",
        "One entry and exactly one exit.",
        "hex", "id{{text}}",
    ),
    _symbol(
        "decision", "Decision", "process", "specific",
        "Rhombus (diamond) with its vertices at the top, bottom, left and right.",
        "A decision or switching-type function with one entry and several alternative "
        "exits, exactly one of which is activated after the condition written inside the "
        "symbol is evaluated. The results of the evaluation are written next to the "
        "flowlines of the respective paths.",
        ["Any test whose outcome selects one of two or more paths.",
         "Loop termination tests when loop limit symbols are not used."],
        ["Leave an exit unlabelled or give two exits the same label.",
         "Give it a single exit - that is a process, not a decision.",
         "Phrase it as a command."],
        "Closed question or comparison: 'Stock >= quantity?', 'Customer known?'.",
        "One entry; two or more exits leaving from the vertices, each labelled with its "
        "outcome (several exits may also branch from one line leaving the symbol).",
        "diam", "id{text}",
    ),
    _symbol(
        "parallel_mode", "Parallel mode", "process", "specific",
        "Two parallel horizontal lines (a double bar) drawn across the flowlines.",
        "Synchronization of two or more parallel operations: paths leaving the symbol "
        "start together; a path below the symbol starts only when all paths entering it "
        "are complete.",
        ["Fork: several operations may run concurrently.",
         "Join: an operation must wait until all concurrent operations have finished."],
        ["Use it for alternative paths - alternatives need a Decision.",
         "Give it a single entry and a single exit."],
        "Normally none; an identifier may be added.",
        "Two or more entries (join) and/or two or more exits (fork).",
        "fork", "id[text]:::iso_parallel_mode", fidelity="approximate",
        note="Mermaid draws a solid bar; the classic syntax has no bar shape.",
    ),
    _symbol(
        "loop_limit", "Loop limit", "process", "specific",
        "Two parts: the beginning is a rectangle with both upper corners cut off; the end "
        "is a rectangle with both lower corners cut off.",
        "Beginning and end of a loop. Both parts carry the same loop identifier. "
        "Initialization, increment and termination condition are written in the "
        "beginning or the end part, depending on where the test is made.",
        ["Counted or conditional loops in structured program flowcharts, instead of a "
         "Decision with a back-edge."],
        ["Use only one part, or give the two parts different identifiers.",
         "Draw an explicit back-edge as well - the pair already implies repetition."],
        "Loop identifier plus the condition, e.g. 'L1: for each order line' ... 'L1: until "
        "end of lines'.",
        "Beginning part: one entry, one exit into the loop body. End part: one entry from "
        "the body, one exit leaving the loop.",
        "notch-pent", "id[/text\\]  (end: id[\\text/])", fidelity="approximate",
        note="Mermaid has a single loop-limit shape; the end part is marked with the "
             "class iso_loopend.",
    ),
    # --------------------------------------------------------------- data family
    _symbol(
        "data", "Data", "data", "basic",
        "Parallelogram with horizontal top and bottom edges, leaning to the right.",
        "Data with the medium unspecified. In program flowcharts it is the usual symbol "
        "for input and output operations.",
        ["Reading or writing data when the medium does not matter.",
         "Any input/output step in a program flowchart."],
        ["Use it for processing that only transforms data in memory."],
        "Verb + data, e.g. 'Read customer record', 'Write invoice'.",
        "One entry and exactly one exit in program flowcharts.",
        "lean-r", "id[/text/]",
    ),
    _symbol(
        "stored_data", "Stored data", "data", "basic",
        "Rectangle whose left and right sides are arcs curving the same way (convex on "
        "the left, concave on the right).",
        "Data stored in a form suitable for processing, the medium being unspecified.",
        ["Files or data stores in data and system flowcharts when the device does not "
         "matter."],
        ["Use it for transient data that is not stored."],
        "Name of the data store, e.g. 'Customer master file'.",
        "Lines from processes that write it; lines to processes that read it.",
        "bow-rect", "id[(text)]:::iso_stored_data", fidelity="exact",
    ),
    _symbol(
        "internal_storage", "Internal storage", "data", "specific",
        "Square or rectangle with one extra line parallel to the top edge and one parallel "
        "to the left edge, close to them.",
        "Data stored in internal (main) storage.",
        ["Showing that data is kept in main memory, e.g. a table loaded into memory."],
        ["Use it for files on external devices."],
        "Name of the in-memory data, e.g. 'Rate table'.",
        "As for other data symbols.",
        "win-pane", "id[text]:::iso_internal_storage", fidelity="exact",
    ),
    _symbol(
        "sequential_access_storage", "Sequential access storage", "data", "specific",
        "Circle with a tangent line drawn horizontally from its bottom point to the right "
        "(a tape reel).",
        "Data stored in sequential access storage, e.g. magnetic tape, tape cartridge or "
        "cassette.",
        ["Files that can only be read or written sequentially."],
        ["Use it for direct-access devices such as disks."],
        "Name of the file, e.g. 'Transaction tape'.",
        "As for other data symbols.",
        "dbl-circ", "id(((text))):::iso_sequential_access_storage", fidelity="approximate",
        note="Mermaid has no tape-reel shape; a double circle marked with the class "
             "iso_sequential_access_storage is used.",
    ),
    _symbol(
        "direct_access_storage", "Direct access storage", "data", "specific",
        "Cylinder lying on its side: horizontal top and bottom lines closed by an "
        "elliptical arc at each end, one end drawn as a full ellipse.",
        "Data stored in direct access storage, e.g. magnetic disk, drum or flexible disk "
        "(today also databases on disk).",
        ["Databases and files accessed by key or address."],
        ["Draw it as a vertical cylinder - that is a common non-ISO variant."],
        "Name of the store, e.g. 'Orders database'.",
        "As for other data symbols.",
        "h-cyl", "id[(text)]:::iso_direct_access_storage", fidelity="exact",
        note="The classic syntax only has a vertical cylinder.",
    ),
    _symbol(
        "document", "Document", "data", "specific",
        "Rectangle whose bottom edge is a single wavy line.",
        "Human-readable data, e.g. printout, OCR or MICR document, microfilm, tally roll, "
        "data entry form.",
        ["Reports, forms, printed output, paper input documents."],
        ["Use it for screen output - that is Display."],
        "Name of the document, e.g. 'Invoice', 'Exception report'.",
        "As for other data symbols. Several overlapping documents show multiple copies.",
        "doc", "id[text]:::iso_document", fidelity="exact",
        note="The classic syntax has no document shape (approximated by a rectangle).",
    ),
    _symbol(
        "manual_input", "Manual input", "data", "specific",
        "Quadrilateral: a rectangle whose top edge slopes upward from left to right.",
        "Data entered manually at the time of processing, e.g. online keyboard, switch "
        "settings, push buttons, light pen, bar-code wand.",
        ["Operator keyboard entry, scanning, pressing buttons during processing."],
        ["Use it for a human task that is not data entry - that is Manual operation."],
        "What is entered, e.g. 'Enter PIN'.",
        "As for other data symbols.",
        "sl-rect", "id[text]:::iso_manual_input", fidelity="exact",
    ),
    _symbol(
        "card", "Card", "data", "specific",
        "Rectangle with its upper-left corner cut off diagonally.",
        "Data with the medium being cards, e.g. punched cards, magnetic cards, mark-sense "
        "cards.",
        ["Card media, including modern magnetic or chip cards when the medium matters."],
        ["Use it as a generic 'record' symbol."],
        "Name of the card data, e.g. 'Time card'.",
        "As for other data symbols.",
        "notch-rect", "id[text]:::iso_card", fidelity="exact",
    ),
    _symbol(
        "punched_tape", "Punched tape", "data", "specific",
        "Rectangle whose top and bottom edges are parallel wavy lines (a ribbon).",
        "Data with the medium being punched tape.",
        ["Legacy paper-tape media (rare today)."],
        ["Use it for magnetic tape - that is Sequential access storage."],
        "Name of the tape data.",
        "As for other data symbols.",
        "flag", "id[text]:::iso_punched_tape", fidelity="exact",
    ),
    _symbol(
        "display", "Display", "data", "specific",
        "Horizontal outline with a pointed, curved left end, straight top and bottom edges "
        "and a rounded right end (a CRT screen silhouette).",
        "Data displayed for human use, e.g. on a screen or online indicator.",
        ["Output shown on a screen, console, indicator or terminal."],
        ["Use it for printed output - that is Document."],
        "What is displayed, e.g. 'Show order summary'.",
        "As for other data symbols.",
        "curv-trap", "id[text]:::iso_display", fidelity="exact",
    ),
    # --------------------------------------------------------------- line family
    _symbol(
        "line", "Line (flowline)", "line", "basic",
        "Solid straight line, drawn horizontally or vertically. An arrowhead at the "
        "destination end is required when the flow is not top-to-bottom or left-to-right "
        "and may be used everywhere for clarity.",
        "Flow of data or control between symbols.",
        ["Every transition between two symbols."],
        ["Leave an end unattached.", "Imply a junction where two lines merely cross."],
        "Decision outcome labels are written beside the line; other lines normally carry "
        "no text.",
        "Incoming lines may join into one outgoing line (junction); crossing lines have "
        "no logical relationship.",
        "-->", "A --> B", model={"edge_kind": "flow"},
    ),
    _symbol(
        "control_transfer", "Control transfer", "line", "specific",
        "A line carrying the control-transfer marking defined by the standard, distinct "
        "from an ordinary flowline, with the arrow toward the process that receives control.",
        "Immediate transfer of control from one process to another, possibly with a direct "
        "return to the initiating process when the initiated process has finished.",
        ["Calls, interrupts or activations between processes in system flowcharts and "
         "program network charts."],
        ["Use it for the ordinary sequence of a program flowchart."],
        "The kind of transfer (call, interrupt, activate) beside the line.",
        "From the initiating to the initiated process.",
        "==>", "A ==> B", fidelity="approximate",
        note="Rendered as a thick arrow.", model={"edge_kind": "control_transfer"},
    ),
    _symbol(
        "communication_link", "Communication link", "line", "specific",
        "Zigzag (lightning-bolt) line; arrowheads show the direction of transfer.",
        "Transfer of data by a telecommunication link.",
        ["Data sent over a network or telecom line in data, system and resources charts."],
        ["Use it for in-program control flow."],
        "Optionally the data or channel transferred.",
        "Between the communicating data or process symbols.",
        "-.->", "A -.->|⚡ text| B", fidelity="approximate",
        note="Rendered as a dotted arrow whose label starts with ⚡.",
        model={"edge_kind": "communication_link"},
    ),
    _symbol(
        "dashed_line", "Dashed line", "line", "specific",
        "Dashed line.",
        "Alternative relationship between two or more symbols; also used to surround an "
        "annotated area and to attach an Annotation.",
        ["Showing that symbols are alternatives.",
         "Attaching an Annotation or enclosing a group of symbols that it explains."],
        ["Use it for ordinary flow."],
        "Normally none.",
        "No flow direction.",
        "-.-", "A -.- B", model={"edge_kind": "dashed"},
    ),
    # ------------------------------------------------------------ special family
    _symbol(
        "terminator", "Terminator", "special", "special",
        "Stadium: a horizontal rectangle whose short sides are semicircles.",
        "Exit to, or entry from, the outside environment: the start or end of a program "
        "flow, external use, or the origin or destination of data. It is also the first "
        "and last symbol of a detailed representation.",
        ["Start and end of a program, routine or detailed representation.",
         "External source or destination of data in data and system charts."],
        ["Use it for intermediate steps or pauses.",
         "Give a start Terminator more than one outgoing flowline.",
         "Draw it as an ellipse or a sharp rectangle."],
        "'Start', 'End', 'Stop', 'Return', or the name of the routine or environment.",
        "Start: no incoming line and exactly one outgoing line. End: incoming line(s) only.",
        "stadium", "id([text])",
    ),
    _symbol(
        "connector", "Connector", "special", "special",
        "Small circle.",
        "Exit to, or entry from, another part of the same chart; used to break a line and "
        "continue it elsewhere (on the same page or another page). Corresponding "
        "connectors carry the same unique identifier.",
        ["Avoiding long or crossing lines.", "Continuing a flow on another page."],
        ["Use it as a GOTO into the middle of a loop or decision structure.",
         "Give two entry (in-)connectors the same identifier."],
        "Short identifier: a letter or number on-page; page-qualified for cross-page "
        "references (e.g. '3A').",
        "Out-connector: incoming line(s), no outgoing line. In-connector: no incoming line, "
        "exactly one outgoing line.",
        "circle", "id((text))",
    ),
    _symbol(
        "annotation", "Annotation", "special", "special",
        "Open rectangle (a bracket open on one side) joined by a dashed line to the "
        "symbol, line or dashed enclosure it explains.",
        "Addition of descriptive comments or explanatory notes for clarification.",
        ["Explanations, formulas, references, assumptions that do not fit in a symbol."],
        ["Connect it with a flowline or make it part of the flow.",
         "Use it to state a condition that changes the flow - that is a Decision."],
        "Free explanatory text.",
        "Attached by a dashed line only; never on the flow path.",
        "brace", "id[text]:::iso_annotation", fidelity="approximate",
        note="Mermaid draws a curly brace; the attachment is a dotted link.",
    ),
    _symbol(
        "ellipsis", "Ellipsis", "special", "special",
        "Three dots ( ... ).",
        "Omission of a symbol or group of symbols whose type and number are not specified.",
        ["Showing a repeated pattern of unspecified length, e.g. 'file 1 ... file n'."],
        ["Hide decision logic or error handling in a program flowchart."],
        "Normally none (the dots themselves).",
        "Placed in the line of omitted symbols.",
        "text", "id[...]:::iso_ellipsis", fidelity="approximate",
    ),
    # ------------------------------------------------------- legacy (non-ISO)
    _symbol(
        "off_page_connector", "Off-page connector (ANSI X3.5 legacy)", "special", "legacy",
        "Pentagon shaped like a baseball home plate (rectangle with a pointed bottom).",
        "Entry from or exit to a flowchart on another page. Defined by ANSI X3.5-1970 and "
        "common on flowchart templates, but not part of ISO 5807, which uses the circular "
        "Connector with a page-qualified identifier for every continuation.",
        ["Only when the whole documentation set has adopted the ANSI X3.5 convention."],
        ["Mix it with page-qualified circle connectors for the same purpose."],
        "Page reference plus identifier, e.g. 'P3-A'.",
        "As for Connector.",
        "odd", "id>text]", fidelity="approximate", standard="ANSI X3.5 (legacy)",
        note="Mermaid has no home-plate shape; the asymmetric shape is used.",
    ),
]

SYMBOLS_BY_ID: Dict[str, Dict[str, object]] = {str(s["id"]): s for s in SYMBOLS}

# Names people commonly use for the symbols, normalized with normalize_key().
TYPE_ALIASES: Dict[str, str] = {
    # terminator
    "terminal": "terminator", "start": "terminator", "end": "terminator", "stop": "terminator",
    "begin": "terminator", "finish": "terminator", "exit": "terminator", "return": "terminator",
    "start_end": "terminator", "startend": "terminator", "terminal_point": "terminator",
    "oval": "terminator", "stadium": "terminator", "pill": "terminator",
    # process
    "rect": "process", "rectangle": "process", "action": "process", "operation": "process",
    "step": "process", "task": "process", "activity": "process", "proc": "process",
    # predefined process
    "predefined": "predefined_process", "subroutine": "predefined_process",
    "subprocess": "predefined_process", "sub_process": "predefined_process",
    "module": "predefined_process", "procedure": "predefined_process",
    "call": "predefined_process", "fr_rect": "predefined_process",
    # manual operation
    "manual": "manual_operation", "manual_op": "manual_operation",
    "manual_task": "manual_operation",
    # preparation
    "prep": "preparation", "prepare": "preparation", "initialization": "preparation",
    "initialisation": "preparation", "init": "preparation", "hexagon": "preparation",
    # decision
    "diamond": "decision", "rhombus": "decision", "condition": "decision",
    "conditional": "decision", "choice": "decision", "branch": "decision", "if": "decision",
    "question": "decision", "test": "decision",
    # parallel mode
    "parallel": "parallel_mode", "fork": "parallel_mode", "join": "parallel_mode",
    "sync": "parallel_mode", "synchronization": "parallel_mode", "synchronisation": "parallel_mode",
    # loop limit
    "loop": "loop_limit", "loop_begin": "loop_limit", "loop_start": "loop_limit",
    "loop_end": "loop_limit", "loop_limit_begin": "loop_limit", "loop_limit_end": "loop_limit",
    # data
    "io": "data", "i_o": "data", "input_output": "data", "inputoutput": "data", "input": "data",
    "output": "data", "parallelogram": "data", "data_io": "data", "read": "data", "write": "data",
    # stored data
    "storage": "stored_data", "stored": "stored_data", "data_store": "stored_data",
    "datastore": "stored_data", "file": "stored_data",
    # internal storage
    "memory": "internal_storage", "ram": "internal_storage", "internal_memory": "internal_storage",
    "main_memory": "internal_storage",
    # sequential access storage
    "tape": "sequential_access_storage", "magnetic_tape": "sequential_access_storage",
    "sequential_storage": "sequential_access_storage",
    # direct access storage
    "database": "direct_access_storage", "db": "direct_access_storage",
    "disk": "direct_access_storage", "magnetic_disk": "direct_access_storage",
    "direct_storage": "direct_access_storage", "das": "direct_access_storage",
    # document
    "doc": "document", "report": "document", "printout": "document", "form": "document",
    # manual input
    "keyboard": "manual_input", "manual_entry": "manual_input", "keyboard_input": "manual_input",
    # card / punched tape / display
    "punched_card": "card", "punch_card": "card",
    "paper_tape": "punched_tape", "punch_tape": "punched_tape",
    "screen": "display", "monitor": "display",
    # connectors
    "circle": "connector", "on_page_connector": "connector", "onpage_connector": "connector",
    "on_page_reference": "connector", "page_connector": "connector",
    "off_page": "off_page_connector", "offpage_connector": "off_page_connector",
    "off_page_reference": "off_page_connector", "offpage": "off_page_connector",
    # annotation / ellipsis
    "comment": "annotation", "note": "annotation", "remark": "annotation",
    "omission": "ellipsis", "dots": "ellipsis", "...": "ellipsis",
}

ROLE_FROM_TYPE_ALIAS = {
    "loop_begin": "begin",
    "loop_start": "begin",
    "loop_limit_begin": "begin",
    "loop_end": "end",
    "loop_limit_end": "end",
}

EDGE_KIND_ALIASES = {
    "": "flow", "flow": "flow", "line": "flow", "flowline": "flow", "flow_line": "flow",
    "solid": "flow", "control": "flow", "sequence": "flow", "data_flow": "flow",
    "dashed": "dashed", "dashed_line": "dashed", "dotted": "dashed", "alternative": "dashed",
    "association": "dashed", "annotation": "dashed",
    "communication_link": "communication_link", "communication": "communication_link",
    "comm_link": "communication_link", "telecom": "communication_link",
    "telecommunication": "communication_link", "zigzag": "communication_link",
    "network": "communication_link",
    "control_transfer": "control_transfer", "transfer": "control_transfer",
    "call": "control_transfer", "interrupt": "control_transfer",
}

DIRECTION_ALIASES = {
    "TB": "TB", "TD": "TB", "TOP_DOWN": "TB", "TOP_TO_BOTTOM": "TB", "DOWN": "TB",
    "LR": "LR", "LEFT_TO_RIGHT": "LR", "LEFT_RIGHT": "LR", "RIGHT": "LR",
    "BT": "BT", "BOTTOM_TO_TOP": "BT", "UP": "BT",
    "RL": "RL", "RIGHT_TO_LEFT": "RL", "LEFT": "RL",
}


def normalize_key(value: object) -> str:
    """Lower-case and turn spaces, hyphens and slashes into underscores."""
    text = str(value).strip().lower()
    if text in ("...", "…"):
        return "..."
    return re.sub(r"[\s\-/]+", "_", text)


def resolve_type(raw: object) -> Tuple[Optional[str], Optional[str]]:
    """Map a user-supplied symbol type to (canonical type, implied loop role)."""
    key = normalize_key(raw)
    if key in NODE_TYPES:
        return key, None
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key], ROLE_FROM_TYPE_ALIAS.get(key)
    return None, None


def suggest_types(raw: object, limit: int = 3) -> List[str]:
    """Closest canonical types for an unknown symbol type."""
    key = normalize_key(raw)
    candidates = list(NODE_TYPES) + list(TYPE_ALIASES)
    suggestions: List[str] = []
    for match in difflib.get_close_matches(key, candidates, n=limit * 2, cutoff=0.6):
        canonical = match if match in NODE_TYPES else TYPE_ALIASES[match]
        if canonical not in suggestions:
            suggestions.append(canonical)
    return suggestions[:limit]


def resolve_symbol_id(raw: object) -> Optional[str]:
    """Resolve a symbol reference (node type, alias or line symbol) to a symbol id."""
    key = normalize_key(raw)
    if key in SYMBOLS_BY_ID:
        return key
    canonical, _ = resolve_type(key)
    if canonical:
        return canonical
    line_aliases = {"flowline": "line", "flow": "line", "flow_line": "line", "arrow": "line",
                    "dashed": "dashed_line", "comm_link": "communication_link",
                    "zigzag": "communication_link", "transfer": "control_transfer"}
    return line_aliases.get(key)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

RULE_CATEGORIES = {
    "symbols": "Core symbols: choice, geometry and meaning",
    "flowlines": "Flowlines: direction, arrowheads, crossings, junctions, line types",
    "connectors": "Connectors: on-page and cross-page continuation",
    "text": "Text, labels and annotation",
    "structure": "Logical integrity of the flow (entries, exits, loops, outcomes)",
    "layout": "Layout, density and granularity",
    "model": "Integrity of the JSON flowchart model used by the tools",
}


def _rule(rid: str, category: str, basis: str, severity: str, check: str, title: str,
          statement: str, rationale: str, fix: str) -> Dict[str, str]:
    return {
        "id": rid, "category": category, "basis": basis, "severity": severity,
        "check": check, "title": title, "rule": statement, "rationale": rationale, "fix": fix,
    }


RULES: List[Dict[str, str]] = [
    # ------------------------------------------------------------------ symbols
    _rule("SYM-01", "symbols", "ISO 5807", "error", "automatic",
          "Use only standard symbols, with their defined meaning",
          "Every symbol is one of the ISO 5807 symbols and is used with the meaning the "
          "standard gives it. Do not invent shapes or reassign meanings.",
          "A closed, shared vocabulary is what makes a flowchart readable by anyone trained "
          "in the standard.",
          "Replace the symbol with the ISO 5807 symbol whose definition matches the step "
          "(see the symbol reference)."),
    _rule("SYM-02", "symbols", "ISO 5807", "info", "manual",
          "Basic symbols by default, specific symbols when the medium or nature matters",
          "The basic symbols (Process, Data, Stored data, Line) may always be used. Use a "
          "specific symbol (Document, Manual operation, Direct access storage, ...) only "
          "when the medium or the nature of the function is known and relevant.",
          "Specific symbols add information; used without need they add noise or false "
          "precision.",
          "Fall back to the basic symbol when the specific medium is irrelevant."),
    _rule("SYM-03", "symbols", "ISO 5807", "info", "manual",
          "Shape carries meaning; size, colour and shading do not",
          "Symbols may be drawn in any size, but their shape must stay recognisable and "
          "their proportions consistent within a chart. Do not rotate or mirror symbols. "
          "Colour, shading and line weight carry no meaning in the standard.",
          "Readers identify symbols by outline; colour may be unavailable (print, "
          "colour-blind readers).",
          "Restore the standard outline; move any meaning carried by colour into text or "
          "an Annotation."),
    _rule("SYM-04", "symbols", "ISO 5807", "error", "automatic",
          "A striped symbol points to a detailed representation",
          "A horizontal stripe near the top of a process or data symbol states that a more "
          "detailed representation exists elsewhere in the same documentation set; the "
          "identifier of that representation is written between the stripe and the top "
          "edge. The detailed chart begins and ends with Terminators.",
          "Striping supports top-down decomposition without breaking the chart's level of "
          "abstraction.",
          "Use detail_ref only on process or data symbols, and give the detailed chart "
          "start/end Terminators."),
    _rule("SYM-05", "symbols", "ISO 5807", "info", "manual",
          "Predefined process names a function specified elsewhere",
          "Use the Predefined process for a named process (subroutine, module, library "
          "function) whose steps are specified elsewhere; use a striped symbol when the "
          "detail is in the same documentation set.",
          "The two mechanisms tell the reader where to look for the detail.",
          "Choose Predefined process for external/reusable routines, striping for detail "
          "within the same documentation."),
    _rule("SYM-06", "symbols", "ISO 5807", "warning", "automatic",
          "Use symbols appropriate to the chart type",
          "Program flowcharts describe control flow: process symbols, special symbols and "
          "(for input/output) the basic Data symbol. Media-specific data symbols and manual "
          "symbols belong to data and system flowcharts. Program network and system "
          "resources charts show structure, not decision logic.",
          "Each of the five ISO chart types answers a different question; mixing their "
          "vocabularies mixes the questions.",
          "Use the basic Data symbol in program flowcharts, or change chart_type to "
          "'system' or 'data'."),
    _rule("SYM-07", "symbols", "ISO 5807", "warning", "automatic",
          "Multiple-symbol convention applies to data symbols",
          "Overlapping copies of a data symbol (e.g. a stack of Documents) represent "
          "several media or files of the same kind. The convention is not used for process "
          "symbols.",
          "A stacked process symbol has no defined meaning.",
          "Remove 'multiple' from process symbols; model parallel work with Parallel mode."),
    _rule("SYM-08", "symbols", "ISO 5807", "error", "automatic",
          "A Terminator is either a start or an end",
          "A Terminator marks entry from or exit to the environment. A start Terminator has "
          "no incoming flowline and exactly one outgoing flowline; an end Terminator has "
          "incoming flowline(s) only.",
          "A Terminator in the middle of the flow makes the boundary of the process "
          "ambiguous.",
          "Split the Terminator into a start and an end, or replace it with a Process."),
    _rule("SYM-09", "symbols", "ISO 5807", "error", "automatic",
          "A Decision has one entry and two or more exits",
          "A Decision evaluates the condition written inside it and activates exactly one "
          "of two or more alternative exits.",
          "A one-exit Decision decides nothing; it is a Process or a modelling gap.",
          "Add the missing outcome path(s) or replace the Decision with a Process."),
    _rule("SYM-10", "symbols", "ISO 5807", "warning", "automatic",
          "Parallel mode synchronizes two or more paths",
          "The Parallel mode symbol (two parallel lines) starts or synchronizes concurrent "
          "operations: it has two or more incoming or two or more outgoing flowlines.",
          "With one entry and one exit there is nothing to synchronize.",
          "Remove the symbol or connect the concurrent paths to it."),
    _rule("SYM-11", "symbols", "ISO 5807", "error", "automatic",
          "Loop limits come in matched pairs with one identifier",
          "A loop limit has a beginning part (upper corners cut off) and an end part (lower "
          "corners cut off) carrying the same loop identifier. Initialization, increment and "
          "termination condition go in the beginning or the end part, according to where "
          "the test is made. The end part must be reachable from the beginning part.",
          "An unmatched loop limit leaves the extent of the loop undefined.",
          "Give both parts the same loop_id and roles 'begin' and 'end'."),
    _rule("SYM-12", "symbols", "ISO 5807", "info", "automatic",
          "Ellipsis shows omitted symbols",
          "The ellipsis indicates omitted symbols whose type and number are not specified. "
          "In program flowcharts it must not hide decision logic or error handling.",
          "Omitted logic cannot be reviewed or tested.",
          "Replace the ellipsis with the actual symbols, or a Predefined process."),
    # ---------------------------------------------------------------- flowlines
    _rule("FLW-01", "flowlines", "ISO 5807", "warning", "automatic",
          "Normal flow direction is top-to-bottom and left-to-right",
          "Lay the chart out so that the main flow runs from top to bottom and from left to "
          "right.",
          "Readers scan in the normal direction; reversing it forces every line to carry an "
          "arrowhead and slows reading.",
          "Use direction TB (or LR)."),
    _rule("FLW-02", "flowlines", "ISO 5807", "warning", "manual",
          "Arrowheads are mandatory against the normal direction",
          "Every flowline whose direction is not the normal one (upward or right-to-left, "
          "e.g. a loop back-edge) carries an arrowhead. Arrowheads may be used on any line "
          "for clarity; in program flowcharts put them on all flowlines.",
          "Without an arrowhead a line is read in the normal direction.",
          "Add arrowheads to all back-edges (the Mermaid generator always draws them)."),
    _rule("FLW-03", "flowlines", "ISO 5807", "info", "manual",
          "Crossing lines have no logical relationship",
          "Two flowlines that cross do not join and have no logical relationship. Keep "
          "crossings to a minimum by moving symbols or using connectors.",
          "Crossings are the main source of misread flowcharts.",
          "Re-arrange symbols, or break one line with a pair of connectors."),
    _rule("FLW-04", "flowlines", "ISO 5807", "info", "manual",
          "Junctions merge incoming lines into one outgoing line",
          "Two or more incoming flowlines may join into a single outgoing flowline. Draw "
          "joins as offset T-junctions with the arrowhead showing the merged direction; "
          "never make a four-way join that looks like a crossing.",
          "A junction must be distinguishable from a crossing.",
          "Offset the joining lines so that each join is a T."),
    _rule("FLW-05", "flowlines", "Practice", "info", "manual",
          "Route lines orthogonally and consistently",
          "Draw flowlines as horizontal and vertical segments. Enter symbols at the top (or "
          "left) and leave at the bottom (or right); Decision exits leave from the vertices.",
          "Orthogonal routing keeps the reading path predictable.",
          "Replace diagonal or curved lines with orthogonal segments."),
    _rule("FLW-06", "flowlines", "Practice", "error", "automatic",
          "Only Decisions (and Parallel mode) branch",
          "In a program flowchart only a Decision (alternative paths) or Parallel mode "
          "(concurrent paths) has more than one outgoing flowline. Every other symbol has "
          "exactly one exit, except end Terminators and out-connectors, which have none.",
          "Two exits from a Process leave the reader guessing which one is taken, or whether "
          "both run.",
          "Insert a Decision for alternatives, or a Parallel mode symbol for concurrency."),
    _rule("FLW-07", "flowlines", "Practice", "error", "automatic",
          "A flowline connects two different symbols",
          "A flowline starts and ends at symbols and never connects a symbol to itself.",
          "An unconditional self-loop never terminates.",
          "Route the repetition through a Decision or use loop limit symbols."),
    _rule("FLW-08", "flowlines", "ISO 5807", "warning", "automatic",
          "Line variants keep their defined meaning",
          "Solid line: flow of data or control. Dashed line: alternative relationship or "
          "annotation attachment. Communication link (zigzag): data transfer over a "
          "telecommunication link. Control transfer: immediate transfer of control between "
          "processes. Program flowcharts use ordinary flowlines.",
          "Line style is part of the symbol vocabulary.",
          "Use kind 'flow' in program flowcharts; reserve the other kinds for system, data "
          "and resources charts."),
    _rule("FLW-09", "flowlines", "Practice", "warning", "automatic",
          "No redundant parallel flowlines",
          "Do not draw two flowlines with the same meaning between the same pair of symbols.",
          "Duplicate lines suggest a distinction that does not exist.",
          "Delete the duplicate line."),
    # --------------------------------------------------------------- connectors
    _rule("CON-01", "connectors", "ISO 5807", "error", "automatic",
          "A connector breaks a line: it is an exit or an entry, never both",
          "An out-connector ends a flowline (incoming line(s), no outgoing line). An "
          "in-connector starts one (no incoming line, exactly one outgoing line). A "
          "connector is never both, and never isolated.",
          "A connector stands for an interrupted line; a line has one continuation.",
          "Split the connector into an out-connector and an in-connector with the same "
          "identifier."),
    _rule("CON-02", "connectors", "ISO 5807", "error", "automatic",
          "Matching connectors carry the same unique identifier",
          "Every out-connector has exactly one in-connector with the same identifier. "
          "Several out-connectors may lead to one in-connector, but one identifier never "
          "marks two in-connectors.",
          "The identifier is the only link between the two halves of the line.",
          "Add the missing partner, rename duplicates, or mark genuine cross-page "
          "references with off_page: true."),
    _rule("CON-03", "connectors", "Practice", "warning", "automatic",
          "Keep connector identifiers short and systematic",
          "Use a single letter or number on-page (A, B, 1). Qualify cross-page identifiers "
          "with the page (e.g. '3A' or 'P3-A') and add the cross-reference.",
          "The connector circle is small; long identifiers do not fit and are hard to match.",
          "Shorten the identifier; move explanations to an Annotation."),
    _rule("CON-04", "connectors", "ISO 5807", "warning", "automatic",
          "Off-page connector is an ANSI X3.5 legacy symbol",
          "ISO 5807 uses the circular Connector for every continuation, on the same or "
          "another page, with a page-qualified identifier. The pentagon off-page connector "
          "comes from ANSI X3.5-1970; use it only if the whole documentation set adopts it.",
          "Strict ISO conformance has one connector symbol.",
          "Use type 'connector' with off_page: true and a page-qualified identifier."),
    _rule("CON-05", "connectors", "Practice", "info", "manual",
          "Connectors must not hide structure",
          "Use connectors to avoid long or crossing lines and to continue across pages. "
          "Never use them to jump into the middle of a loop or decision structure, and "
          "prefer a direct line when it is short and uncluttered.",
          "Connector jumps are the flowchart equivalent of GOTO.",
          "Restructure the flow so that every connector continues a single line."),
    # --------------------------------------------------------------------- text
    _rule("TXT-01", "text", "ISO 5807", "warning", "automatic",
          "Minimum text inside symbols",
          "Write only the text needed to understand the function inside a symbol; put "
          "explanations, formulas and references in an Annotation.",
          "Long text forces large symbols and hides the structure.",
          "Shorten the text to verb + object (about 60 characters, 50 for Decisions) and "
          "move the rest to an Annotation."),
    _rule("TXT-02", "text", "ISO 5807", "info", "manual",
          "Text reads left-to-right and top-to-bottom",
          "Text inside and beside symbols is written to be read from left to right and top "
          "to bottom, whatever the direction of flow.",
          "Rotated text breaks the reader's scanning pattern.",
          "Keep all text horizontal."),
    _rule("TXT-03", "text", "ISO 5807", "error", "automatic",
          "Label every Decision exit with its outcome",
          "Write the outcome (Yes/No, >0/=0/<0, ...) beside each exit flowline of a "
          "Decision. Each label is unique within that Decision.",
          "An unlabelled exit makes the condition unreadable.",
          "Add a distinct label to every outgoing flowline of the Decision."),
    _rule("TXT-04", "text", "ISO 5807", "info", "manual",
          "Place symbol identifiers and descriptions outside the symbol",
          "A symbol identifier (for cross-reference with other documentation) is placed "
          "outside the symbol near its top, consistently on the same side throughout the "
          "chart; a symbol description may be placed beside it. A striped symbol's "
          "reference goes inside the stripe.",
          "Identifiers link the chart to code listings and other documents without "
          "cluttering the symbol text.",
          "Move identifiers out of the symbol text."),
    _rule("TXT-05", "text", "Practice", "warning", "automatic",
          "Process text is an imperative action",
          "Phrase process and operation text as verb + object ('Calculate tax'). A question "
          "inside a process symbol hides a Decision.",
          "Consistent grammar tells the reader what kind of step it is before reading the "
          "shape.",
          "Rephrase as a command, or turn the step into a Decision."),
    _rule("TXT-06", "text", "Practice", "info", "automatic",
          "Decision text is a testable condition",
          "Phrase Decision text as a closed question or comparison ('Stock >= quantity?') "
          "whose outcomes are mutually exclusive.",
          "Vague conditions ('Order OK?') hide several tests and their failure cases.",
          "Rewrite the condition so that it can be evaluated to exactly one outcome."),
    _rule("TXT-07", "text", "Practice", "warning", "automatic",
          "Every symbol carries text",
          "Every symbol except Parallel mode, Loop limit (which carries its identifier) and "
          "Ellipsis carries text. A Decision without a condition or a connector without an "
          "identifier is meaningless.",
          "An empty symbol is an unexplained step.",
          "Add the missing text."),
    _rule("TXT-08", "text", "ISO 5807", "error", "automatic",
          "Annotations attach with a dashed line and never carry flow",
          "An Annotation is joined by a dashed line to the symbol, line or dashed enclosure "
          "it explains. It is not part of the flow: no flowline enters or leaves it.",
          "Annotations explain; they must never change the path.",
          "Attach the annotation with 'annotates' (or a dashed edge) and remove flowlines "
          "to or from it."),
    _rule("TXT-09", "text", "Practice", "info", "manual",
          "Use consistent vocabulary",
          "Use one term per concept across the chart and its documentation set, and define "
          "abbreviations in a legend or Annotation.",
          "Synonyms make readers look for differences that do not exist.",
          "Standardize the terms and add a legend."),
    # ---------------------------------------------------------------- structure
    _rule("STR-01", "structure", "Practice", "error", "automatic",
          "Flow begins and ends at boundary symbols",
          "Every path starts at a start Terminator (or an in-connector) and ends at an end "
          "Terminator (or an out-connector). In data and system flowcharts data symbols may "
          "also be sources and sinks.",
          "A flow that starts or stops at an ordinary step has an undefined boundary.",
          "Add the missing start/end Terminator or connect the dangling symbol."),
    _rule("STR-02", "structure", "Practice", "warning", "automatic",
          "Single entry per program flowchart",
          "A program flowchart (or each routine) has exactly one start Terminator; other "
          "entry points belong in their own charts.",
          "Several entries make it unclear which path runs first.",
          "Split the chart per entry point, or merge the starts."),
    _rule("STR-03", "structure", "Practice", "error", "automatic",
          "Every symbol is reachable",
          "Each symbol can be reached from an entry point.",
          "Unreachable symbols are dead logic or a missing connection.",
          "Connect the symbols to the flow or delete them."),
    _rule("STR-04", "structure", "Practice", "error", "automatic",
          "Every path can terminate",
          "From every symbol some path leads to an end Terminator or out-connector.",
          "Otherwise the flow is trapped in a dead end or an endless loop.",
          "Add the missing exit path."),
    _rule("STR-05", "structure", "Practice", "error", "automatic",
          "Every loop has an exit condition",
          "Each cycle contains a Decision (or a loop limit test) with an exit that leaves "
          "the cycle.",
          "A cycle without an exit is an infinite loop.",
          "Add a Decision with an exit (e.g. a maximum number of attempts)."),
    _rule("STR-06", "structure", "Practice", "warning", "automatic",
          "Decision outcomes are complete",
          "The exits of a Decision cover every possible outcome: two-way Decisions use "
          "complementary labels (Yes/No, >=/<), multi-way Decisions include an 'otherwise' "
          "exit.",
          "Uncovered outcomes are the missing failure states that cause defects.",
          "Make the labels complementary or add an 'Otherwise' exit."),
    _rule("STR-07", "structure", "Practice", "warning", "automatic",
          "No redundant Decisions",
          "A Decision whose exits all lead to the same symbol has no effect.",
          "It adds a test without changing the behaviour.",
          "Remove the Decision or route its outcomes differently."),
    _rule("STR-08", "structure", "Practice", "info", "heuristic",
          "Model failure states",
          "Every operation that can fail (input/output, external call, validation, payment, "
          "approval) is followed by a Decision that tests its outcome, and the failure path "
          "is handled (notify, compensate, retry with a limit).",
          "Happy-path-only charts hide the cases that matter most in production.",
          "Add an outcome Decision after the operation and model the failure path."),
    _rule("STR-09", "structure", "ISO 5807", "warning", "automatic",
          "Data flowcharts alternate data and processing",
          "In a data flowchart each processing symbol has data symbols on its input and "
          "output sides, and the chart begins and ends with data symbols (or special "
          "symbols).",
          "A data flowchart documents what data each phase consumes and produces.",
          "Add the data consumed or produced by the processing step."),
    # ------------------------------------------------------------------- layout
    _rule("LAY-01", "layout", "Practice", "warning", "automatic",
          "Limit symbols per page",
          "Keep about 30 or fewer symbols on one page; decompose larger flows with "
          "Predefined processes or striped symbols.",
          "Working memory, not paper size, limits what a reader can follow.",
          "Extract coherent sub-flows into Predefined processes or detailed "
          "representations."),
    _rule("LAY-02", "layout", "Practice", "info", "heuristic",
          "Keep one level of abstraction per chart",
          "All symbols in one chart describe steps at the same granularity; finer detail "
          "goes into a lower-level chart.",
          "Mixed levels hide the overall flow and the detail at the same time.",
          "Raise code-level steps to business steps (or the reverse) and move the detail "
          "into Predefined processes."),
    _rule("LAY-03", "layout", "Practice", "info", "heuristic",
          "Factor out repeated logic",
          "Identical steps or step sequences that appear more than once become one "
          "Predefined process.",
          "Repetition multiplies maintenance and hides the common structure.",
          "Define the repeated logic once and reference it with a Predefined process."),
    _rule("LAY-04", "layout", "Practice", "info", "manual",
          "Align and space symbols uniformly",
          "Draw symbols of one type at one size, aligned on a grid with even spacing; the "
          "main path runs straight, alternatives branch to one side and rejoin below.",
          "Visual regularity lets the reader see the logic instead of the drawing.",
          "Re-align the chart on a grid."),
    _rule("LAY-05", "layout", "Practice", "info", "automatic",
          "Identify the chart",
          "Give each chart a title; in a documentation set also give page number, version, "
          "author and date.",
          "Charts are referenced and revised; an anonymous chart cannot be.",
          "Add a title."),
    # -------------------------------------------------------------------- model
    _rule("MOD-01", "model", "Schema", "error", "automatic",
          "Symbol ids are unique and non-empty",
          "Each node has a non-empty id that no other node uses.",
          "Flowlines refer to symbols by id.",
          "Give every node a unique id."),
    _rule("MOD-02", "model", "Schema", "error", "automatic",
          "References point to existing symbols",
          "Every flowline endpoint and every 'annotates' reference names an existing node.",
          "A dangling reference is a line to nowhere.",
          "Fix the id or add the missing node."),
    _rule("MOD-03", "model", "Schema", "error", "automatic",
          "The model is well-formed",
          "The flowchart is an object with a 'nodes' array (and usually an 'edges' array) "
          "whose items are objects with the documented fields.",
          "The tools cannot interpret anything else.",
          "Follow the flowchart JSON schema."),
]

RULES_BY_ID: Dict[str, Dict[str, str]] = {r["id"]: r for r in RULES}


def symbol_reference(symbol: Optional[str] = None, family: Optional[str] = None,
                     chart_type: Optional[str] = None) -> Dict[str, object]:
    """Return symbol entries, optionally filtered (raises KeyError if unknown)."""
    if symbol:
        sid = resolve_symbol_id(symbol)
        if not sid:
            raise KeyError(symbol)
        return {"standard": STANDARD, "symbol": SYMBOLS_BY_ID[sid]}
    entries = SYMBOLS
    if family:
        entries = [s for s in entries if s["family"] == family]
    if chart_type:
        discouraged: Tuple[str, ...] = ()
        if chart_type == "program":
            discouraged = PROGRAM_CHART_DISCOURAGED
        elif chart_type in ("program_network", "system_resources"):
            discouraged = STRUCTURE_CHART_DISCOURAGED
        entries = [s for s in entries if s["id"] not in discouraged]
    return {
        "standard": STANDARD,
        "chart_type": CHART_TYPES.get(chart_type or "", None),
        "count": len(entries),
        "symbols": entries,
    }


def rules_reference(category: Optional[str] = None, rule_id: Optional[str] = None,
                    basis: Optional[str] = None) -> Dict[str, object]:
    """Return rules, optionally filtered (raises KeyError for an unknown rule id)."""
    if rule_id:
        key = rule_id.strip().upper()
        if key not in RULES_BY_ID:
            raise KeyError(rule_id)
        return {"standard": STANDARD, "rule": RULES_BY_ID[key]}
    entries = RULES
    if category:
        entries = [r for r in entries if r["category"] == category]
    if basis:
        entries = [r for r in entries if r["basis"].lower().startswith(basis.lower())]
    return {
        "standard": STANDARD,
        "categories": RULE_CATEGORIES if not category else {category: RULE_CATEGORIES[category]},
        "count": len(entries),
        "rules": entries,
    }


CHECK_LABELS = {"automatic": "checked", "heuristic": "analysis", "manual": "judgment"}
BASIS_LABELS = {"ISO 5807": "ISO", "Practice": "Practice", "Schema": "Schema"}


def rule_index_markdown(category: Optional[str] = None) -> str:
    """Every rule as a compact Markdown index (embedded in SKILL.md, printed by `rules`).

    Rules that no tool can check from a JSON model ("judgment") carry their full statement,
    because whoever draws the chart has to apply them unaided.
    """
    lines: List[str] = []
    for key, description in RULE_CATEGORIES.items():
        if category and key != category:
            continue
        lines += [f"**{description}**", ""]
        for rule in RULES:
            if rule["category"] != key:
                continue
            tags = (f"{BASIS_LABELS[rule['basis']]}, {rule['severity']}, "
                    f"{CHECK_LABELS[rule['check']]}")
            line = f"- `{rule['id']}` {rule['title']} ({tags})"
            if rule["check"] == "manual":
                line += f": {rule['rule']}"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def rule_detail_text(rule_id: str) -> str:
    """One rule in full, as plain text (raises KeyError for an unknown id)."""
    rule = RULES_BY_ID[rule_id.strip().upper()]
    return (f"{rule['id']}  {rule['title']}\n"
            f"Basis: {rule['basis']} | default severity: {rule['severity']} | "
            f"check: {CHECK_LABELS[rule['check']]} | category: {rule['category']}\n"
            f"Rule: {rule['rule']}\n"
            f"Why:  {rule['rationale']}\n"
            f"Fix:  {rule['fix']}\n")
