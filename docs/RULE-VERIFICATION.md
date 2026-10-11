# Rule verification record

This record covers the cross-verification of the 52 rules and 26 symbols this skill
encodes: the 25 ISO 5807 symbols plus one template symbol. Last run: 2026-10-11.

Enforcement after the review:

| Enforcement | Rules |
|---|---|
| Checked | 37 |
| Analysis | 3 |
| Partly checked | 2 |
| Judgment | 10 |

## Method

Each rule was checked three ways.

1. **Against the standard.** Every rule and symbol with basis *ISO* was compared with the
   text of ISO 5807:1985, read through **GB/T 1526-1989**. That is China's *identical*
   (IDT) adoption of ISO 5807:1985. Its top-level clause numbers are one higher than
   ISO's: GB 10.4 is ISO 9.4, and GB 11.2.1 is ISO 10.2.1. Excerpts of the ISO text itself
   were used where available. For the off-page connector, the sources were IBM's
   *Flowcharting Techniques* (C20-8152) and a catalogue record of the IBM flowcharting
   template.
2. **Against the checker.** [`tests/test_rule_coverage.py`](../tests/test_rule_coverage.py)
   gives each of the 40 checked and analysis rules a violating chart and a conformant twin.
   - On the violating chart, the rule must fire with its documented severity.
   - On the conformant chart, it must stay silent.
   - The two partly checked rules are probed on the symptom the checker sees: SYM-03 on
     Mermaid outlines, SYM-05 on a striped Predefined process.
   - The suite fails when a rule that is not marked judgment has no probe.
   - It also fails when the code reports a rule marked judgment.
   - Twenty-one structural rules are probed again after a round trip through Mermaid, so
     Mermaid input is checked like JSON.
3. **Across the documents.** Each rule's statement, basis, severity and enforcement label was
   compared across the knowledge base, the guide (including the 1.9 checklist), `SKILL.md`,
   the README and the claude.ai project instructions. Tests now keep these parts in step:
   - the `SKILL.md` rule index, which is generated from the knowledge base;
   - the coverage of the 1.9 checklist;
   - this record's rule table.

## Corrections made

### Against the standard

| Rule or symbol | Was | Now (source) |
|---|---|---|
| CON-04, off-page connector | The pentagon was called an ANSI X3.5-1970 symbol. | It comes from IBM flowcharting templates, which list it with transmittal tape and keying as IBM's own additions. Neither ISO 5807 nor ANSI X3.5-1970 defines it; both use the circle with a cross-reference. |
| SYM-03 | "Do not rotate or mirror symbols"; "any size". | Any orientation is allowed, horizontal preferred. A mirror image means the same but is not recommended. Keep the standard outlines and angles, and keep sizes as uniform as possible (GB 11.1). |
| TXT-04 | Identifier "outside, near the top, on a consistent side". | Identifier at the upper left of the symbol, description at the upper right (GB 11.1.4, 11.1.5). |
| SYM-12 | Only a reminder in program flowcharts. | The ellipsis goes only on or between flowlines (GB 10.4.4). The checker now warns about a detached ellipsis; default severity is warning. |
| SYM-02 | "The basic symbols may always be used." | The standard's wording: use a basic symbol when the nature or medium is unknown or need not be shown, and a specific symbol when it is known and must be shown. |
| FLW-01 / FLW-05 | Entering at the top or left and leaving at the bottom or right was filed under Practice. | It is an ISO flowline convention (ISO 10.2.1), so it now belongs to FLW-01. FLW-05 keeps orthogonal routing and consistent outcome placement (practice). |
| SYM-04 | The detailed chart begins and ends with Terminators. | Also: the first Terminator carries the reference written in the stripe (the standard's example uses "XB4"). |
| SYM-07 | Data symbols only. | Adds the standard's examples (files, report copies, report or card formats), front-to-back order for an ordered set, and that lines may attach anywhere on the stack. |
| SYM-06 | Program flowcharts include the basic Data symbol. | ISO builds program flowcharts from process, line and special symbols. The basic Data symbol for input/output is accepted practice. |
| Process symbol | Changes value, form or location. | Also covers determining which of several flow directions is followed. FLW-06, a practice rule, still requires a Decision for every branch. |
| TXT-01 | Annotation for long text. | Also: a separate page with a cross-reference when an Annotation would clutter the chart (GB 11.1.3). |

### Checker behaviour

| Rule | Was | Now |
|---|---|---|
| STR-06 | The exhaustive three-way comparison `<0`, `=0`, `>0` (the guide's own example) got a "no Otherwise exit" warning. | Accepted as complete. Overlapping sets such as `<0`, `=0`, `>=0` are still flagged. |
| SYM-12 | A detached ellipsis passed unnoticed. | Warning. |
| SYM-03, SYM-05 | Marked judgment, although the checker reports SYM-03 for non-ISO Mermaid outlines and SYM-05 for a striped Predefined process. | New enforcement label, *partly checked*; both are probed. SYM-03's default severity is warning, matching what the checker reports. |
| STR-08 | Default severity info. | Warning, the severity the analyzer reports. |
| Analyzer | The parallel-join bottleneck advisory was tagged SYM-10. | Untagged like the other bottleneck advisories; it is not a SYM-10 violation. |

### Documents

| Topic | Was | Now |
|---|---|---|
| Stored data in program flowcharts | The checker warned (SYM-06), but the guide recommended Stored data for any store and the skill named only media-specific symbols. | Everywhere: program flowcharts use only the basic Data symbol; Stored data belongs to data and system flowcharts. |
| FLW-06 scope | The skill and the checklist said "only Decisions and Parallel mode branch" for every chart. | "In program flowcharts", as the rule and the checker say. |
| Lenient mode | Docs said the pentagon is "allowed only in lenient mode". | Strict checks report it as a warning (the chart stays valid); lenient mode stops reporting it. |
| Practice rules | "The validator still enforces it." | Checked wherever the tools can; four practice rules are judgment and three are analysis. |
| Structure rules | Described as all Practice and all validator-enforced. | STR-09 is ISO; STR-08 is an analysis finding. |
| TXT-06 | The guide and the skill asked for positive, quantified questions; the rule did not. | The rule asks for positive wording, plus threshold and unit for numeric conditions. |
| CON-03 | Unconditional cross-reference in the rule, optional in the guide. | The page-qualified identifier is the cross-reference; written text such as "to page 3" is optional. The checker's thresholds are stated. |
| STR-07 | "Reach the same symbol" (reads as reachability). | "Lead directly to the same symbol", as checked. |
| LAY-03 | The guide allowed deliberate redundancy; the rule did not. | The rule allows it with an explaining Annotation. |
| LAY-04 / FLW-05 | "Main path straight" was attributed to FLW-05. | LAY-04. |
| Sub-process mapping | The skill mapped every sub-process to a Predefined process. | Detailed in the same documentation: striped Process; specified elsewhere: Predefined process (SYM-05). |
| Design step 3 in `SKILL.md` | Fallible operations omitted input/output; ends omitted out-connectors and data sinks. | Both added (STR-08, STR-01). |
| 1.9 checklist | Omitted STR-03, STR-07, STR-09 and MOD-01 to MOD-03. | All 52 rules are covered, and a test checks the enforcement column. |
| Symbol classes (1.2) | The special symbols sat in the "specific" column. | Neither basic nor specific. |

## Not verifiable with the sources available

- **Control transfer drawing.** The standard defines a distinct marking for this line. No
  accessible source reproduced it, so the skill describes it without inventing a shape and
  renders it as a thick arrow.
- **The standard's table of which symbols each chart type uses.** SYM-06 follows the
  chart-type definitions, which were verified. The consolidated table was not found.
- **ISO 10.3.1, multiple exits.** The Decision definition (ISO 9.2.2.4) says the outcome
  *may* be written beside each exit line and refers to 10.3.1, which was not found. The
  skill makes the labels mandatory (TXT-03, error), because an unlabelled exit cannot be
  read.

## Rule by rule

Basis: ISO = provision of ISO 5807:1985; Practice = professional practice beyond the
standard; Schema = the JSON model. Clause references are ISO 5807 unless marked GB
(GB/T 1526-1989). *Probed* means `tests/test_rule_coverage.py` checks the rule.

| Rule | Basis | Source check | Checker | Result |
|---|---|---|---|---|
| SYM-01 | ISO | Symbol set of clauses 9.1 to 9.4 (GB 10.1 to 10.4): 10 data, 7 process, 4 line, 4 special symbols | Probed; Mermaid outline misuse probed | Confirmed |
| SYM-02 | ISO | GB definition of basic and specific symbols | Judgment | Corrected |
| SYM-03 | ISO | GB 11.1 | Partly checked (Mermaid outlines); probed | Corrected |
| SYM-04 | ISO | GB 11.1.6; Terminators of a detailed representation (9.4.2) | Probed | Refined |
| SYM-05 | ISO | 9.2.2.1 Predefined process | Partly checked (striped Predefined process); probed | Confirmed |
| SYM-06 | ISO | Chart-type definitions; consolidated table not found | Probed | Refined, partly verified |
| SYM-07 | ISO | Multiple-symbol convention (ISO excerpt) | Probed | Refined |
| SYM-08 | ISO | 9.4.2 Terminator (GB 10.4.2) | Probed | Confirmed |
| SYM-09 | ISO | 9.2.2.4 Decision | Probed | Confirmed |
| SYM-10 | ISO | 9.2.2.5 Parallel mode | Probed | Confirmed |
| SYM-11 | ISO | 9.2.2.6 Loop limit | Probed | Confirmed |
| SYM-12 | ISO | 9.4.4 Ellipsis (GB 10.4.4) | Probed (new placement check) | Corrected |
| FLW-01 | ISO | 10.2.1 standard flow direction, line entry and exit | Probed | Refined |
| FLW-02 | ISO | 10.2.1 use of arrowheads | Judgment; generator draws every arrowhead | Confirmed |
| FLW-03 | ISO | 10.2.1 crossing flowlines | Judgment | Confirmed |
| FLW-04 | ISO | 10.2.1 junctions (offset, arrowheads) | Judgment | Confirmed |
| FLW-05 | Practice | Not an ISO provision | Judgment; generator requests right angles | Narrowed to routing |
| FLW-06 | Practice | ISO lets the basic Process pick a direction; the skill requires a Decision | Probed | Confirmed as practice; scope fixed in docs |
| FLW-07 | Practice | Not an ISO provision | Probed | Confirmed |
| FLW-08 | ISO | 9.3 line symbols (GB 10.3); control-transfer drawing not found | Probed | Partly verified |
| FLW-09 | Practice | Not an ISO provision | Probed | Confirmed |
| CON-01 | ISO | 9.4.1 Connector (GB 10.4.1) | Probed | Confirmed |
| CON-02 | ISO | 9.4.1 Connector: corresponding connectors share an identifier | Probed | Confirmed |
| CON-03 | Practice | Not an ISO provision | Probed | Wording aligned, thresholds stated |
| CON-04 | ISO | 9.4.1 (one connector symbol); IBM C20-8152 and IBM template record | Probed, strict and lenient | Corrected |
| CON-05 | Practice | Not an ISO provision | Judgment | Confirmed |
| TXT-01 | ISO | GB 11.1.3 | Probed | Refined |
| TXT-02 | ISO | GB 11.1.3: text reads left to right, top to bottom, whatever the flow | Judgment; generator writes horizontal text | Confirmed |
| TXT-03 | ISO | 9.2.2.4: results written beside the exit lines; 10.3.1 not found | Probed | Confirmed; the strictness is the skill's |
| TXT-04 | ISO | GB 11.1.4, 11.1.5 | Judgment | Corrected |
| TXT-05 | Practice | Not an ISO provision | Probed | Confirmed |
| TXT-06 | Practice | Not an ISO provision | Probed | Wording aligned |
| TXT-07 | Practice | Not an ISO provision | Probed | Confirmed |
| TXT-08 | ISO | 9.4.3 Annotation (GB 10.4.3) | Probed | Confirmed |
| TXT-09 | Practice | Not an ISO provision | Judgment | Confirmed |
| STR-01 | Practice | Not an ISO provision | Probed | Confirmed |
| STR-02 | Practice | Not an ISO provision | Probed | Confirmed |
| STR-03 | Practice | Not an ISO provision | Probed | Confirmed |
| STR-04 | Practice | Not an ISO provision | Probed | Confirmed |
| STR-05 | Practice | Not an ISO provision | Probed | Confirmed |
| STR-06 | Practice | Not an ISO provision | Probed (three-way comparison too) | Corrected |
| STR-07 | Practice | Not an ISO provision | Probed | Wording aligned |
| STR-08 | Practice | Not an ISO provision | Probed (analysis) | Severity corrected |
| STR-09 | ISO | Data flowchart clause: begins and ends with data symbols; process symbols preceded and followed by data | Probed | Confirmed |
| LAY-01 | Practice | Not an ISO provision | Probed | Confirmed |
| LAY-02 | Practice | Not an ISO provision | Probed (analysis) | Confirmed |
| LAY-03 | Practice | Not an ISO provision | Probed (analysis) | Exception added |
| LAY-04 | Practice | Uniform sizes are ISO (now also in SYM-03); grid alignment is practice | Judgment | Confirmed |
| LAY-05 | Practice | Not an ISO provision | Probed | Confirmed |
| MOD-01 | Schema | JSON model | Probed | Confirmed |
| MOD-02 | Schema | JSON model | Probed | Confirmed |
| MOD-03 | Schema | JSON model | Probed | Confirmed |

## Sources

- ISO 5807:1985, *Information processing: Documentation symbols and conventions for data,
  program and system flowcharts, program network charts and system resources charts*.
- GB/T 1526-1989, *信息处理 数据流程图、程序流程图、系统流程图、程序网络图和系统资源图的文件编制符号及约定*,
  identical adoption of ISO 5807:1985 (full-text reprint at uml.org.cn).
- IBM, *Flowcharting Techniques*, C20-8152 (its symbols come from template X20-8020), and
  the Centre for Computing History's record of an IBM flowcharting template: standard
  symbols plus three IBM-specific ones (offpage connector, transmittal tape, keying).
- N. Chapin, "Flowcharting with the ANSI standard: a tutorial," *ACM Computing Surveys*
  2(2), 1970.
