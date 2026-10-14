"""Phase 3: SAP metadata catalog.

A small, honest catalog of SAP objects (function modules/BAPIs, structures, tables) kept in YAML
files under knowledge_base/catalog/. Every entry carries a status:

  verified    checked against a real SAP system or the official SAP documentation (source given)
  documented  taken from a written source (source given) but not checked in a system
  unverified  written from general knowledge - useful as a hint, NOT proof

The catalog is used two ways: facts for the objects a question mentions are put in front of the
LLM, and the names the LLM then uses in its code are checked against the catalog."""
