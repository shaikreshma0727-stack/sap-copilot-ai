"""Pipeline tests with the offline hash embedder (they check plumbing, not semantic quality;
semantic quality is measured with `python -m app.rag.cli eval` using the real model)."""

import pytest

from app.rag.embedder import HashEmbedder
from app.rag.ingest import ingest_folder
from app.rag.retriever import Retriever
from app.rag.store import KnowledgeStore

PR_NOTE = """# Purchase requisition BAPI

Use BAPI_PR_CREATE to create a purchase requisition. Items are passed in table PRITEM and
the new requisition number comes back in NUMBER. Call BAPI_TRANSACTION_COMMIT afterwards.
The requisition data is stored in table EBAN (items) in the MM module.
"""

SQL_CLASS = """CLASS zcl_sql DEFINITION PUBLIC.
  PUBLIC SECTION.
    METHODS join_demo.
ENDCLASS.
CLASS zcl_sql IMPLEMENTATION.
  METHOD join_demo.
    SELECT a~carrid, b~connid FROM scarr AS a INNER JOIN spfli AS b ON a~carrid = b~carrid INTO TABLE @DATA(lt).
  ENDMETHOD.
ENDCLASS.
"""

CDS = "define view entity ZI_Flight as select from sflight { key carrid }\n"


@pytest.fixture()
def kb(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "pr_note.md").write_text(PR_NOTE, encoding="utf-8")
    (src / "zcl_sql.clas.abap").write_text(SQL_CLASS, encoding="utf-8")
    (src / "zi_flight.ddls.asddls").write_text(CDS, encoding="utf-8")
    (src / "image.png").write_bytes(b"\x89PNG")  # unsupported -> ignored
    store = KnowledgeStore(tmp_path / "chroma")
    embedder = HashEmbedder()
    report = ingest_folder(src, "demo", store, embedder)
    return store, embedder, report


def test_ingest_report_and_count(kb):
    store, _, report = kb
    assert report.files_seen == 3  # png ignored
    assert report.files_chunked == 3
    assert store.count() == report.chunks > 0


def test_reingest_is_idempotent_and_replaces_source(kb, tmp_path):
    store, embedder, report = kb
    before = store.count()
    ingest_folder(tmp_path / "src", "demo", store, embedder)
    assert store.count() == before  # no duplicates
    (tmp_path / "src" / "pr_note.md").unlink()
    ingest_folder(tmp_path / "src", "demo", store, embedder)
    assert store.count() < before  # deleted file no longer searchable


@pytest.mark.parametrize("mode", ["hybrid", "vector", "bm25"])
def test_exact_bapi_name_found_in_every_mode(kb, mode):
    store, embedder, _ = kb
    hits = Retriever(store, embedder).search("BAPI_PR_CREATE", k=3, mode=mode)
    assert hits and "BAPI_PR_CREATE" in hits[0].text


def test_partial_identifier_word_matches_via_bm25(kb):
    store, embedder, _ = kb
    hits = Retriever(store, embedder).search("requisition number", k=3, mode="bm25")
    assert hits and hits[0].metadata["path"] == "pr_note.md"


def test_hybrid_merges_both_rankings(kb):
    store, embedder, _ = kb
    top = Retriever(store, embedder).search("INNER JOIN carrid", k=3, mode="hybrid")[0]
    assert top.metadata["object_type"] == "method"
    assert top.vector_rank is not None and top.bm25_rank is not None
    assert top.score > 1.0 / 61  # got contributions from both lists


def test_metadata_filters(kb):
    store, embedder, _ = kb
    r = Retriever(store, embedder)
    only_cds = r.search("flight", k=5, filters={"object_type": "cds_view_entity"})
    assert only_cds and all(h.metadata["object_type"] == "cds_view_entity" for h in only_cds)
    mm = r.search("requisition", k=5, mode="bm25", filters={"module": "MM"})
    assert mm and all(h.metadata["module"] == "MM" for h in mm)
    assert r.search("requisition", k=5, filters={"module": "FI"}, mode="bm25") == []
    both = r.search("requisition", k=5, filters={"module": "MM", "object_type": "doc_section"})
    assert both and both[0].metadata["path"] == "pr_note.md"


def test_empty_store_returns_nothing(tmp_path):
    r = Retriever(KnowledgeStore(tmp_path / "empty"), HashEmbedder())
    assert r.search("anything") == []


def test_bm25_index_refreshes_after_new_ingest(kb, tmp_path):
    store, embedder, _ = kb
    r = Retriever(store, embedder)
    assert r.search("zzzuniqueword", k=3, mode="bm25") == []
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "n.md").write_text("# Notes\n\nThe word zzzuniqueword appears in this very long enough note body text.", encoding="utf-8")
    ingest_folder(extra, "extra", store, embedder)
    assert r.search("zzzuniqueword", k=3, mode="bm25")


def test_invalid_mode_rejected(kb):
    store, embedder, _ = kb
    with pytest.raises(ValueError):
        Retriever(store, embedder).search("x", mode="nope")
