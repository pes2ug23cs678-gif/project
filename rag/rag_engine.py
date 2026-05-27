"""RAG engine — ingests COBOL files into the knowledge base.

Reads COBOL source files, checks their knowledge-base status, chunks them
by procedure/paragraph, and persists the chunks for later retrieval.

Usage (always run as a module from the project root):
    python -m rag.rag_engine

The engine auto-discovers every *.cob / *.cbl / *.cpy / *.cobol file
under the ``data/`` directory, so no hardcoded filenames are needed.
"""

from __future__ import annotations

import glob
import os

from preprocessing.preprocessor import (
    file_exists,
    save_to_knowledge_base,
    check_list_not_empty,
    check_kb_status,
    chunk_by_procedure,
    filter_cobol_files,
)

# ---------------------------------------------------------------------------
# COBOL file discovery
# ---------------------------------------------------------------------------

_COBOL_GLOBS = ["*.cob", "*.cbl", "*.cpy", "*.cobol", "*.CBL", "*.COB"]
_DATA_DIR = "data"


def _discover_cobol_files(data_dir: str = _DATA_DIR) -> list[str]:
    """Return all COBOL source files found recursively under *data_dir*."""
    found: list[str] = []
    for pattern in _COBOL_GLOBS:
        found.extend(glob.glob(os.path.join(data_dir, "**", pattern), recursive=True))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in found:
        norm = os.path.normpath(p)
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the RAG ingestion pipeline."""
    # Auto-discover all COBOL files under data/ (no hardcoded filenames)
    corpus = _discover_cobol_files(_DATA_DIR)

    if not check_list_not_empty(corpus, f"no COBOL files found under '{_DATA_DIR}/' — "
                                        "place .cob/.cbl/.cpy/.cobol files there and re-run"):
        return

    # Keep only files whose KB entry is missing or outdated
    kb_folder = os.path.join(_DATA_DIR, "knowledge_base")
    stale_files = [
        f for f in corpus
        if check_kb_status(f, kb_folder) in ("MISSING", "OUTDATED")
    ]
    if not check_list_not_empty(stale_files, "all files are already up-to-date in KB"):
        return

    # Filter to recognized COBOL extensions (defensive — already filtered by glob)
    cobol_files = filter_cobol_files(stale_files)
    if not check_list_not_empty(cobol_files, "no COBOL files to process"):
        return

    # Chunk and persist
    ingested = 0
    for cobol_file in cobol_files:
        with open(cobol_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        chunks = chunk_by_procedure(raw_text)
        for chunk in chunks:
            save_to_knowledge_base(chunk, metadata={"source": cobol_file})
        ingested += 1
        print(f"  [OK] Ingested: {cobol_file}  ({len(chunks)} chunk(s))")

    print(f"\nIngestion complete — {ingested} file(s) added to knowledge base.")


if __name__ == "__main__":
    main()
