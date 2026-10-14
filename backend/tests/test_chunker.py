from app.rag.chunker import MAX_CHARS, chunk_abap, chunk_bdef, chunk_cds, chunk_file, chunk_markdown, detect_module, detect_syntax_era, split_lines

ABAP_CLASS = '''"! <p class="shorttext">Demo class</p>
"! Reads purchase requisitions.
CLASS zcl_demo DEFINITION PUBLIC FINAL CREATE PUBLIC.
  PUBLIC SECTION.
    INTERFACES if_oo_adt_classrun.
    METHODS get_pr IMPORTING iv_banfn TYPE eban-banfn.
ENDCLASS.

CLASS zcl_demo IMPLEMENTATION.
  "Reads one requisition
  METHOD get_pr.
    SELECT SINGLE * FROM eban WHERE banfn = @iv_banfn INTO @DATA(ls_eban).
  ENDMETHOD.

  METHOD if_oo_adt_classrun~main.
    out->write( |hello| ).
  ENDMETHOD.
ENDCLASS.
'''

ABAP_CLASSIC = '''REPORT zprog_old.
TABLES: eban.
DATA: lt_eban TYPE TABLE OF eban.

START-OF-SELECTION.
  SELECT * FROM eban INTO TABLE lt_eban.
  PERFORM show_data.

FORM show_data.
  LOOP AT lt_eban INTO eban.
    WRITE: / eban-banfn.
  ENDLOOP.
ENDFORM.
'''


def _by_type(chunks, t):
    return [c for c in chunks if c.metadata["object_type"] == t]


def test_abap_class_split_into_definition_and_methods():
    chunks = chunk_abap(ABAP_CLASS, "src/zcl_demo.clas.abap", "demo")
    types = [c.metadata["object_type"] for c in chunks]
    assert types.count("class_definition") == 1
    assert types.count("method") == 2
    names = {c.metadata["object_name"] for c in _by_type(chunks, "method")}
    assert names == {"zcl_demo=>get_pr", "zcl_demo=>if_oo_adt_classrun~main"}


def test_abap_doc_and_comments_attached_to_block():
    chunks = chunk_abap(ABAP_CLASS, "src/zcl_demo.clas.abap", "demo")
    definition = _by_type(chunks, "class_definition")[0]
    assert "Reads purchase requisitions" in definition.text  # ABAP Doc above the CLASS statement
    get_pr = next(c for c in _by_type(chunks, "method") if c.metadata["method_name"] == "get_pr")
    assert "Reads one requisition" in get_pr.text  # comment above METHOD


def test_methods_do_not_leak_into_each_other():
    chunks = chunk_abap(ABAP_CLASS, "src/zcl_demo.clas.abap", "demo")
    get_pr = next(c for c in _by_type(chunks, "method") if c.metadata["method_name"] == "get_pr")
    assert "hello" not in get_pr.text
    main = next(c for c in _by_type(chunks, "method") if c.metadata["method_name"].endswith("main"))
    assert "eban" not in main.text.lower().split("\n", 1)[1]


def test_deferred_class_is_not_a_block():
    src = "CLASS lcl_a DEFINITION DEFERRED.\nCLASS lcl_a DEFINITION.\n  PUBLIC SECTION.\n    METHODS x.\nENDCLASS.\n"
    chunks = chunk_abap(src, "src/z.clas.locals_def.abap", "demo")
    assert [c.metadata["object_type"] for c in chunks] == ["class_definition"]
    assert chunks[0].metadata["object_name"] == "lcl_a"


def test_classic_report_form_and_report_block():
    chunks = chunk_abap(ABAP_CLASSIC, "src/zprog_old.prog.abap", "demo")
    types = {c.metadata["object_type"] for c in chunks}
    assert {"form", "report_block"} <= types
    form = _by_type(chunks, "form")[0]
    assert form.metadata["object_name"] == "show_data"
    assert form.metadata["syntax_era"] == "classic"
    assert form.metadata["module"] in ("general", "MM")
    block = _by_type(chunks, "report_block")[0]
    assert block.metadata["object_name"] == "zprog_old"
    assert "START-OF-SELECTION" in block.text


def test_metadata_is_chroma_safe_primitives():
    for c in chunk_abap(ABAP_CLASS, "src/zcl_demo.clas.abap", "demo") + chunk_markdown("# T\n\nsome text that is long enough to keep around here ok", "a.md", "demo"):
        for k, v in c.metadata.items():
            assert isinstance(v, (str, int, float, bool)), (k, v)


def test_long_method_is_split_with_overlap_and_size_limit():
    body = "\n".join(f"    lv_{i} = {i}. \"statement number {i}" for i in range(400))
    src = f"CLASS c IMPLEMENTATION.\n  METHOD big.\n{body}\n  ENDMETHOD.\nENDCLASS.\n"
    chunks = [c for c in chunk_abap(src, "src/c.clas.abap", "demo") if c.metadata["object_type"] == "method"]
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS * 1.25 for c in chunks)
    assert [c.metadata["part"] for c in chunks] == list(range(1, len(chunks) + 1))
    assert all(c.metadata["parts"] == len(chunks) for c in chunks)
    # overlap: last lines of window 1 reappear at the start of window 2
    tail = chunks[0].text.splitlines()[-1]
    assert tail in chunks[1].text


def test_split_lines_prefers_blank_line_and_handles_long_line():
    lines = ["a" * 50] * 20 + [""] + ["b" * 50] * 20
    windows = split_lines(lines, max_chars=1100, overlap=2)
    assert len(windows) >= 2
    assert split_lines(["x" * 5000], max_chars=1000)[0][0] == "x" * 1000


def test_cds_and_bdef():
    cds = "@EndUserText.label: 'x'\ndefine root view entity ZI_Travel as select from ztravel { key id }\n"
    c = chunk_cds(cds, "src/zi_travel.ddls.asddls", "demo")[0]
    assert c.metadata["object_type"] == "cds_view_entity" and c.metadata["object_name"] == "ZI_Travel"
    assert c.metadata["technology"] == "cds"
    b = chunk_bdef("managed implementation in class zbp unique;\ndefine behavior for ZI_Travel alias Travel\n{ create; }", "src/x.bdef.asbdef", "demo")[0]
    assert b.metadata["object_type"] == "behavior_definition" and b.metadata["technology"] == "rap"
    assert b.metadata["object_name"] == "ZI_Travel"


MD = """# ABAP Cheat Sheet

Intro paragraph that is long enough to be kept as its own chunk in the index.

## Internal Tables

Text about internal tables with enough words to count as real content here.

``` abap
# this hash line is code, not a heading
DATA(itab) = VALUE string_table( ( `a` ) ( `b` ) ).
```

### Reading

Use READ TABLE or table expressions to read single rows from an internal table.
"""


def test_markdown_sections_breadcrumbs_and_fences():
    chunks = chunk_markdown(MD, "docs/01_Internal_Tables.md", "demo")
    names = [c.metadata["object_name"] for c in chunks]
    assert "ABAP Cheat Sheet > Internal Tables" in names
    assert "ABAP Cheat Sheet > Internal Tables > Reading" in names
    code_chunk = next(c for c in chunks if c.metadata["object_name"].endswith("Internal Tables"))
    assert code_chunk.metadata["has_code"] is True
    assert "# this hash line is code" in code_chunk.text  # not mistaken for a heading
    assert not any("this hash line" in n for n in names)


def test_chunk_file_dispatch_and_unknown_extension():
    assert chunk_file("x", "a.png", "s") == []
    assert chunk_file(ABAP_CLASS, "z.clas.abap", "s")


def test_detect_module_and_era():
    assert detect_module("CALL FUNCTION 'BAPI_PR_CREATE' ... SELECT FROM eban") == "MM"
    assert detect_module("A story about Mara and the master plan") == "general"
    assert detect_syntax_era("DATA(x) = 1.", "abap") == "modern"
    assert detect_syntax_era("TABLES: eban.\nMOVE a TO b.", "abap") == "classic"
    assert detect_syntax_era("DATA(x) = 1.\nWRITE: / x.", "abap") == "mixed"
