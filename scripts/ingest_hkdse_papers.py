#!/usr/bin/env python3
"""Ingest HKDSE past papers and marking schemes into knowledge bases.

Scans ``HKDSE_Paper/<Subject>/`` and builds curriculum vector stores so that the
Market generation/marking tools can ground their output in verified, school-held
documents (Retrieval-Augmented Generation).

Routing
-------
  • Question papers   → KB  ``hkdse-<subject>``            (e.g. hkdse-chinese)
  • Marking schemes   → KB  ``hkdse-<subject>-marking``    (answer/ms/解答 files)

A file is treated as a marking scheme if it lives in an ``answer*`` folder or its
name contains a marking-scheme marker (ms / answer / marking / 解答 / 答案 / 評卷).

Usage
-----
    python3 scripts/ingest_hkdse_papers.py --dry-run     # classify only, no indexing
    python3 scripts/ingest_hkdse_papers.py               # build / update the KBs
    python3 scripts/ingest_hkdse_papers.py --subject Math
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPERS_ROOT = PROJECT_ROOT / "HKDSE_Paper"

# Folder name (as on disk) → KB slug.
SUBJECT_SLUGS = {
    "Chinese": "chinese",
    "English": "english",
    "Math": "math",
    "Maths": "math",
    "Mathematics": "math",
}

MARKING_MARKERS = ("ms", "answer", "marking", "marksheme", "解答", "答案", "評卷", "评卷", "參考")


def _is_marking_scheme(pdf: Path) -> bool:
    parts_lower = [p.lower() for p in pdf.parts]
    if any("answer" in p for p in parts_lower):
        return True
    name = pdf.name.lower()
    return any(marker in name for marker in MARKING_MARKERS)


def classify() -> dict[str, list[Path]]:
    """Return {kb_name: [pdf, ...]} for all discovered papers."""
    routing: dict[str, list[Path]] = {}
    if not PAPERS_ROOT.exists():
        print(f"error: {PAPERS_ROOT} not found", file=sys.stderr)
        sys.exit(1)

    for subject_dir in sorted(PAPERS_ROOT.iterdir()):
        if not subject_dir.is_dir():
            continue
        slug = SUBJECT_SLUGS.get(subject_dir.name)
        if not slug:
            print(f"  (skipping unknown subject folder: {subject_dir.name})")
            continue
        for pdf in sorted(subject_dir.rglob("*.pdf")):
            kb = f"hkdse-{slug}-marking" if _is_marking_scheme(pdf) else f"hkdse-{slug}"
            routing.setdefault(kb, []).append(pdf)
    return routing


async def ingest(routing: dict[str, list[Path]], subject_filter: str | None) -> None:
    from deeptutor.knowledge.manager import KnowledgeBaseManager
    from deeptutor.services.rag.service import RAGService

    manager = KnowledgeBaseManager()
    existing = set(manager.list_knowledge_bases())
    rag = RAGService()

    for kb_name, pdfs in routing.items():
        if subject_filter and subject_filter.lower() not in kb_name:
            continue
        file_paths = [str(p) for p in pdfs]
        print(f"\n→ {kb_name}  ({len(file_paths)} file(s))")
        for p in pdfs:
            print(f"    - {p.relative_to(PROJECT_ROOT)}")
        try:
            if kb_name in existing:
                ok = await rag.add_documents(kb_name, file_paths)
            else:
                ok = await rag.initialize(kb_name, file_paths)
                existing.add(kb_name)
            print(f"    {'✓ indexed' if ok else '✗ pipeline returned False'}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ✗ failed: {exc}")
            print("      (check the embedding provider in Settings → Catalog; "
                  "for offline use, point it at a local embedding model)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest HKDSE papers into knowledge bases.")
    parser.add_argument("--dry-run", action="store_true", help="classify only; do not index")
    parser.add_argument("--subject", help="limit to one subject slug (chinese | english | math)")
    args = parser.parse_args()

    routing = classify()
    print("Classification:")
    for kb_name, pdfs in routing.items():
        kind = "marking scheme" if kb_name.endswith("-marking") else "question paper"
        print(f"  {kb_name}  [{kind}]  → {len(pdfs)} file(s)")

    if args.dry_run:
        print("\n(dry run — nothing indexed)")
        return

    asyncio.run(ingest(routing, args.subject))
    print("\nDone. Use these KB names in the Market tools' 'Knowledge Base' field.")


if __name__ == "__main__":
    main()
