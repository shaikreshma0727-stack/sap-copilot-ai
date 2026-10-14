# SAP catalog (Phase 3)

YAML files in this folder describe SAP objects the copilot should know exactly:
function modules / BAPIs, structures, tables and table types.

## Status - be honest, it is shown to users

| status       | meaning                                                                 |
|--------------|-------------------------------------------------------------------------|
| `verified`   | you checked it in a real SAP system (SE37 / SE11) or in official docs; `source` is required |
| `documented` | copied from a written source (`source` required) but not checked in a system |
| `unverified` | written from general knowledge - a hint, NOT proof                       |

The files shipped with the project are all `unverified` seed data. When you (or a colleague with
system access) check an entry in SE37 / SE11, change its status to `verified` and put the check in
`source`, e.g. `source: "SE37 on S/4HANA 2023 sandbox, 2026-10-20"`.

`complete: true` means the parameter / field list is the full list; then any other name is reported
as a conflict. Keep `complete: false` unless you compared with the real object.

**Never copy TCS or client objects, specs or data into this folder.** Standard SAP objects only.

## Entry format

```yaml
- name: BAPI_EXAMPLE
  kind: function_module        # function_module | structure | table | table_type
  module: MM
  description: One line.
  keywords: [purchase requisition, create pr]   # lower-case phrases that should surface this entry
  status: unverified
  source: ""
  complete: false
  params:                      # direction from the function module's side: import | export | tables | changing
    - {name: HEADER, direction: import, type: BAPIHEADER}
  notes: Optional hint.
```

Structures and tables use `fields:` (names, or `{name, type, key}`); a table type uses `line_type:`.

## Commands (run inside backend/ with the venv on)

```bash
python -m app.catalog.cli validate
python -m app.catalog.cli stats
python -m app.catalog.cli show BAPI_PR_CREATE
python -m app.catalog.cli check some_code.abap
```
