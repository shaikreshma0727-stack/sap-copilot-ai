# Interview question bank

YAML files in this folder feed the Interview coach (`/interview/...`, the "Interview coach" tab).

```yaml
- id: itab-types                 # unique short word, never reuse
  topic: Internal tables
  level: basic                   # basic | intermediate | advanced
  question: "What are the three kinds of internal tables, and when do you use each?"
  key_points:                    # at least 2 things a good answer says
    - text: "Standard tables are accessed by index; key access is a linear search."
      any: [standard, "index+linear"]   # lower-case; point counts as covered if ANY entry is found
  model_answer: "Short reference answer, shown after the user answers."
  source: "general knowledge - review before relying on it"
```

`"a+b"` inside `any` means both words must appear.

## How the score works (be honest about it)

Score (0-10) = share of the key points the answer covers. A point counts as covered when one of its
keywords is found; points that were not found are then checked by the AI, which can accept an answer
that says the same thing in other words. Without an LLM key only keywords are used. It measures
"did you mention the expected points", not overall answer quality.

## Quality

The shipped questions were written by the assistant from general ABAP knowledge and are NOT reviewed
against SAP documentation. Read each one, correct what is wrong and change `source:` to where you checked it.
Add your own questions in your own words. Do not copy questions or answers from TCS or client material.

## Commands (inside backend/ with the venv on)

```bash
python -m app.interview.cli validate
python -m app.interview.cli list
```
