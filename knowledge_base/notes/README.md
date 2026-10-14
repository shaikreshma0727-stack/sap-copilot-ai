# Your own notes (the most valuable part of the knowledge base)

Open-source samples teach the ABAP language, but they contain very little classic
SAP business material (purchase requisition BAPIs, tables like EBAN, BADIs, exits).
That knowledge comes from YOU. Write short Markdown notes in this folder, one topic per file.

## Rules
- Write only things you know to be correct. Check BAPI/table details in your own system (SE37, SE11) before writing them down.
- Do NOT paste employer or client code, specs or data. Only write general knowledge and your own examples.
- One topic per file, with clear headings. Include exact technical names (BAPI names, table names, parameters).

## Template (copy into a new file, e.g. purchase_requisition_bapi.md)

```
# Purchase requisition creation (MM)

## Which BAPI
(name of the BAPI you verified in SE37, and when to use it)

## Parameters
(importing / tables parameters that matter, with the structure types)

## Tables involved
(e.g. EBAN: purchase requisition items; what key fields mean)

## Typical call sequence
(BAPI call, error handling with RETURN, COMMIT)

## Minimal example
(a short, correct ABAP snippet you have tested)
```

After adding or changing notes, re-ingest them:

    cd backend
    python -m app.rag.cli ingest ../knowledge_base/notes --source my-notes
