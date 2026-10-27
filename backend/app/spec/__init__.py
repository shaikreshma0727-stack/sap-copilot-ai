"""FS to TS: turn a functional specification into a technical specification draft.

Three honest layers:
  1. checklist.py  - fixed list of topics a technical spec needs (selection screen, authorization, error
                     handling, ...). Reports which topics the FS text mentions and which it does not, and
                     the question to ask the functional consultant for each missing one. No AI involved.
  2. detect.py     - SAP objects named in the FS: those known to the catalog (with their status) and
                     custom Z/Y names. Nothing is guessed.
  3. draft.py      - optional LLM draft of the TS that must put everything the FS does not say under
                     "Open questions" instead of inventing it.
"""
