"""Code review mode: paste ABAP, get findings you can verify line by line.

Three honest layers:
  1. rules.py   - fixed pattern rules (SELECT in a loop, FOR ALL ENTRIES without an empty check, obsolete
                  statements, ...). Heuristics on the text: they can have false positives and cannot see
                  table types or data volumes. Every finding carries a line number and the reason.
  2. abaplint   - grammar and declaration check, when abaplint is installed (see Phase 4).
  3. assess.py  - optional LLM review that gets the code with line numbers and the findings above, and has to
                  say what it could not judge.
This is not a replacement for ATC / Code Inspector in your SAP system.
"""
