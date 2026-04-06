"""RAG engine — ingests COBOL files into the knowledge base.

Reads COBOL source files, checks their knowledge-base status, chunks them
by procedure/paragraph, and persists the chunks for later retrieval.
"""

from __future__ import annotations

from preprocessing.preprocessor import (
    file_exists,
    save_to_knowledge_base,
    check_list_not_empty,
    check_kb_status,
    chunk_by_procedure,
    filter_cobol_files,
)


def main() -> None:
    """Run the RAG ingestion pipeline."""
    corpus = [
        "data/Form1.cob",
        "data/Global.asax.cob",
        "data/Program1.cob",
    ]

    if not check_list_not_empty(corpus, "corpus is empty"):
        return

    # Keep only files that exist on disk
    good_corpus = [f for f in corpus if file_exists(f)]
    if not check_list_not_empty(good_corpus, "no files found at the specified paths"):
        return

    # Keep only files whose KB entry is missing or outdated
    kb_folder = "data/knowledge_base"
    stale_files = [
        f for f in good_corpus
        if check_kb_status(f, kb_folder) in ("MISSING", "OUTDATED")
    ]
    if not check_list_not_empty(stale_files, "all files are already up-to-date in KB"):
        return

    # Filter to recognized COBOL extensions
    cobol_files = filter_cobol_files(stale_files)
    if not check_list_not_empty(cobol_files, "no COBOL files to process"):
        return

    # Chunk and persist
    for cobol_file in cobol_files:
        with open(cobol_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        chunks = chunk_by_procedure(raw_text)
        for chunk in chunks:
            save_to_knowledge_base(chunk, metadata={"source": cobol_file})
    print(f"Ingested {len(cobol_files)} file(s) into knowledge base.")


if __name__ == "__main__":
    main()
