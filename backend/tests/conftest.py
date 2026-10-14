"""Test environment: runs before any test module imports the app.

The KB tests use the offline 'hash' embedder and a throw-away folder, so the test
suite never downloads a model and never touches your real knowledge_base/."""

import os
import tempfile

os.environ.setdefault("EMBEDDING_BACKEND", "hash")
os.environ.setdefault("KB_DIR", tempfile.mkdtemp(prefix="sap_kb_test_"))
