# Error knowledge

YAML files in this folder feed the Error analyzer (`POST /errors/analyze`, the "Error analyzer" tab).

```yaml
- id: time-out                       # unique short word, never reuse
  title: "Dialog work process time limit exceeded (TIME_OUT)"
  runtime_errors: [TIME_OUT]         # ST22 runtime error names (upper case)
  exceptions: []                     # exception classes, e.g. CX_SY_ZERODIVIDE
  phrases: ["time limit exceeded"]   # lower-case fragments of an error message
  causes: ["..."]                    # at least 1
  fix_steps: ["..."]                 # at least 1
  tcodes: [ST22, SAT]
  status: unverified                 # verified | documented | unverified
  source: "general knowledge - review before relying on it"
```

An entry needs at least one of `runtime_errors`, `exceptions`, `phrases`.

## How matching works

The pasted text is parsed first (runtime error, exception, program, include, line, message class/number),
then every entry is scored: runtime error name 10 points, exception class 6, each phrase found 3.
The top 3 are shown. Keep `phrases` specific; a generic phrase like "does not exist" matches many texts.

## Quality

The shipped entries were written by the assistant from general SAP knowledge and are NOT checked against SAP
documentation or a real system. Read each one, correct it, and change `status` and `source` to where you checked it.
Add entries from errors you solved yourself, in your own words. Do not copy material from TCS or client projects,
and never put real dump data (user names, customer data, system IDs) in these files.
