"""Consolidated preprocessing utilities for the COBOL-to-Python migration pipeline.

This module merges functionality from the former helper_number1–5 modules into
a single, cleanly named module.

Functions
---------
file_exists          – Check whether a filesystem path exists.
compute_file_hash    – Return the MD5 hex-digest of a file.
save_to_knowledge_base – Persist a text chunk to the knowledge-base folder.
check_list_not_empty – Guard: print a warning and return False when a list is empty.
is_in_list           – Case-insensitive membership check.
check_kb_status      – Compare source file against the knowledge-base copy.
chunk_by_procedure   – Split COBOL text on paragraph/section headers.
filter_cobol_files   – Keep only filenames with recognised COBOL extensions.
"""

from __future__ import annotations

import hashlib
import os
import re


# ---------------------------------------------------------------------------
# File utilities  (formerly helper_number1)
# ---------------------------------------------------------------------------

def file_exists(path: str) -> bool:
    """Return ``True`` if *path* exists on the filesystem."""
    return os.path.exists(path)


def compute_file_hash(path: str) -> str:
    """Return the MD5 hex-digest of the file at *path*."""
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def save_to_knowledge_base(
    chunk: str,
    metadata: dict,
    output_folder: str = "./data/knowledge_base",
) -> None:
    """Write a text *chunk* to a uniquely-named file inside *output_folder*."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    source_name = os.path.basename(metadata["source"]).split(".")[0]
    chunk_id = hashlib.md5(chunk.encode()).hexdigest()[:8]
    file_path = os.path.join(output_folder, f"{source_name}_{chunk_id}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(chunk)


# ---------------------------------------------------------------------------
# List / string helpers  (formerly helper_number2)
# ---------------------------------------------------------------------------

def check_list_not_empty(items: list, label: str) -> bool:
    """Return ``True`` if *items* is non-empty, otherwise print a warning."""
    if len(items) == 0:
        print(f"Warning: empty list — {label}")
        return False
    return True


def is_in_list(value: str, items: list[str]) -> bool:
    """Case-insensitive membership check."""
    return value.lower() in items


# ---------------------------------------------------------------------------
# Knowledge-base status  (formerly helper_number3)
# ---------------------------------------------------------------------------

def check_kb_status(source_file: str, kb_folder: str) -> str:
    """Compare *source_file* against its knowledge-base counterpart.

    Returns
    -------
    ``"MISSING"``   – KB copy does not exist.
    ``"OUTDATED"``  – KB copy exists but hash differs.
    ``"EXISTS"``    – KB copy is up-to-date.
    """
    file_name = os.path.basename(source_file)
    kb_path = os.path.join(kb_folder, file_name)
    if not file_exists(kb_path):
        return "MISSING"
    source_hash = compute_file_hash(source_file)
    destination_hash = compute_file_hash(kb_path)
    if source_hash != destination_hash:
        return "OUTDATED"
    return "EXISTS"


# ---------------------------------------------------------------------------
# COBOL text chunker  (formerly helper_number4)
# ---------------------------------------------------------------------------

def chunk_by_procedure(text: str) -> list[str]:
    """Split COBOL *text* on paragraph / section headers (e.g. ``UPDATE-LOGIC.``)."""
    sections = re.split(r"\n([A-Z0-9\-]+\.)", text)
    chunks: list[str] = []
    for i in range(1, len(sections), 2):
        chunk = sections[i] + sections[i + 1]
        chunks.append(chunk.strip())
    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# COBOL file filter  (formerly helper_number5)
# ---------------------------------------------------------------------------

_COBOL_EXTENSIONS = {"cob", "cbl", "ccp", "cpy", "cobol"}


def filter_cobol_files(file_list: list[str]) -> list[str]:
    """Return only entries from *file_list* whose extension is a known COBOL type."""
    result: list[str] = []
    for entry in file_list:
        entry = entry.strip()
        ext = entry.rsplit(".", 1)[-1] if "." in entry else ""
        if is_in_list(ext, list(_COBOL_EXTENSIONS)):
            result.append(entry)
    return result
