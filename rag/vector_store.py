"""Semantic RAG engine using ChromaDB + sentence-transformers."""

import os
import chromadb
from chromadb.utils import embedding_functions
from preprocessing.preprocessor import chunk_by_procedure

EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "cobol_patterns"
PERSIST_DIR = os.path.normpath("./data/vector_store")

_client = chromadb.PersistentClient(path=PERSIST_DIR)
_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)


def get_collection():
    """Get or create the collection for COBOL patterns."""
    return _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_ef,
    )


def ingest_knowledge_base(kb_dir: str = "data/knowledge_base") -> int:
    """Embed and store all KB documents into ChromaDB.
    
    Returns the number of ingested chunks/documents.
    """
    if not os.path.exists(kb_dir):
        return 0

    collection = get_collection()
    count = 0

    for fname in os.listdir(kb_dir):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(kb_dir, fname)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        if not content:
            continue

        # If it's a pattern template file, ingest it as a single unit
        if fname.startswith("cobol_"):
            doc_id = f"pattern_{fname}"
            collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[{"source": fname, "type": "pattern"}],
            )
            count += 1
        else:
            # Reference COBOL programs: chunk by procedure
            chunks = chunk_by_procedure(content)
            for i, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk:
                    continue
                doc_id = f"ref_{fname}_{i}"
                collection.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[{"source": fname, "type": "reference", "chunk_index": i}],
                )
                count += 1
    return count


def retrieve(query_cobol: str, top_k: int = 3) -> list[dict]:
    """Retrieve top-K most relevant KB documents."""
    collection = get_collection()
    results = collection.query(
        query_texts=[query_cobol],
        n_results=top_k,
    )

    docs = []
    if not results or not results["documents"] or not results["documents"][0]:
        return docs

    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        docs.append({
            "content": doc,
            "source": meta["source"],
            "type": meta.get("type", "unknown"),
            "relevance_score": float(1.0 - distance),
        })
    return docs
