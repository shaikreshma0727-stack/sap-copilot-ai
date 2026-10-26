"""Error analyzer: paste an ST22 short dump or an SAP error message and get the likely cause,
fix steps and transactions to check.

Three honest layers:
  1. parser.py   - deterministic extraction of facts that are literally in the pasted text
                   (runtime error, exception class, program, line, message class/number, ...).
  2. knowledge   - YAML entries in knowledge_base/errors/ matched against those facts. Every entry
                   carries a status (verified / documented / unverified); shipped ones are unverified.
  3. LLM         - optional explanation written from layers 1 and 2. Without a key, layers 1 and 2 still work.
"""
