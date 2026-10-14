#!/usr/bin/env bash
# Downloads open-source ABAP sample repos into knowledge_base/raw/ (shallow clones, ~20 MB total).
# Run from the project root:   bash scripts/fetch_sources.sh
# All repos below are published by SAP under the Apache-2.0 license. Their folders are
# git-ignored: they are source material for search, not part of your project.
set -u
cd "$(dirname "$0")/.." || exit 1
mkdir -p knowledge_base/raw
cd knowledge_base/raw || exit 1

clone() {
  local name="$1" url="$2"
  if [ -d "$name/.git" ]; then
    echo "== $name already present (updating)"
    git -C "$name" pull --ff-only --depth 1 2>/dev/null || true
  else
    echo "== cloning $name"
    GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 "$url" "$name" || echo "!! could not clone $name (skipping)"
  fi
}

# Core: ABAP language cheat sheets with runnable example classes, CDS and RAP samples
clone abap-cheat-sheets https://github.com/SAP-samples/abap-cheat-sheets
clone cloud-abap-rap https://github.com/SAP-samples/cloud-abap-rap

# Optional extras (more RAP material). Uncomment to add them:
# clone abap-platform-rap-opensap https://github.com/SAP-samples/abap-platform-rap-opensap
# clone abap-platform-refscen-flight https://github.com/SAP-samples/abap-platform-refscen-flight

echo
echo "Done. Next: cd backend && python -m app.rag.cli ingest ../knowledge_base/raw/abap-cheat-sheets --source abap-cheat-sheets"
