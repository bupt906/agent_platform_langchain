#!/usr/bin/env python3
"""
chunk_document.py — Split a plain-text document into overlapping chunks with
stable ids, snapping chunk ends to sentence/paragraph boundaries where possible.

Deterministic (no LLM, no network). Standard library only.

Usage:
    python chunk_document.py input.txt --out out.chunks.json
    python chunk_document.py input.txt --out out.chunks.json --size 1200 --overlap 150
    python chunk_document.py input.txt --docid report2024 --unit chars --size 4000 --overlap 600

Sizes are in approximate tokens by default (~4 chars/token). Use --unit chars to
specify exact character counts, or --unit words for whitespace words.

Output JSON:
{
  "doc_id": "report2024",
  "source": "input.txt",
  "unit": "tokens", "size": 1200, "overlap": 150,
  "chunks": [
    {"id": "report2024.c0", "text": "...", "start_char": 0, "end_char": 4800, "est_tokens": 1180}
  ]
}
"""
import argparse
import json
import os
import re
import sys

CHARS_PER_TOKEN = 4  # rough, model-agnostic approximation
# Sentence-ish boundary:
# - English: ., !, ? followed by optional closing quotes/brackets and whitespace.
# - Chinese: 。, ！, ？ followed by optional closing quotes/brackets; whitespace is
#   optional because Chinese prose often has no spaces between sentences.
# - Blank line: paragraph break.
_BOUNDARY = re.compile(
    r'(?:[.!?][\"\'\)\]\}”’）】》」』]?\s)'
    r'|(?:[。！？][\"\'\)\]\}”’）】》」』]?\s*)'
    r'|(?:\n\s*\n)'
)


def est_tokens(text):
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def to_chars(size, overlap, unit, text):
    """Convert a requested size/overlap in the chosen unit into character counts."""
    if unit == "chars":
        return int(size), int(overlap)
    if unit == "tokens":
        return int(size) * CHARS_PER_TOKEN, int(overlap) * CHARS_PER_TOKEN
    if unit == "words":
        words = text.split()
        avg = (sum(len(w) for w in words) / len(words) + 1) if words else 6
        return int(size * avg), int(overlap * avg)
    raise ValueError(f"unknown unit: {unit}")


def snap_end(text, start, hard_end):
    """Move the chunk end back to the last sentence/paragraph boundary that falls
    within the final ~30% of the window, so we cut at a natural break. If none is
    found, fall back to the last whitespace; if still none, use the hard cut."""
    if hard_end >= len(text):
        return len(text)
    window_floor = start + int((hard_end - start) * 0.7)
    last = None
    for m in _BOUNDARY.finditer(text, window_floor, min(hard_end + 1, len(text))):
        last = m.end()
    if last and last > start:
        return last
    ws = text.rfind(" ", window_floor, hard_end)
    if ws != -1 and ws > start:
        return ws + 1
    return hard_end


def chunk_text(text, size_chars, overlap_chars):
    if overlap_chars >= size_chars:
        overlap_chars = max(0, size_chars // 5)
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        hard_end = min(start + size_chars, n)
        end = snap_end(text, start, hard_end)
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, end, piece))
        if end >= n:
            break
        step = end - overlap_chars
        start = step if step > start else end  # always make progress
    return chunks


def main():
    ap = argparse.ArgumentParser(description="Chunk a text document with overlap.")
    ap.add_argument("input", help="Path to a UTF-8 text file.")
    ap.add_argument("--out", required=True, help="Where to write the chunks JSON.")
    ap.add_argument("--docid", default=None,
                    help="Stable document id (default: input filename stem).")
    ap.add_argument("--unit", choices=["tokens", "chars", "words"], default="tokens")
    ap.add_argument("--size", type=int, default=1200, help="Chunk size in --unit.")
    ap.add_argument("--overlap", type=int, default=150, help="Overlap in --unit.")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    docid = args.docid or re.sub(r"[^A-Za-z0-9_-]", "_",
                                 os.path.splitext(os.path.basename(args.input))[0])

    size_chars, overlap_chars = to_chars(args.size, args.overlap, args.unit, text)
    raw = chunk_text(text, size_chars, overlap_chars)

    chunks = [
        {"id": f"{docid}.c{i}", "text": piece,
         "start_char": s, "end_char": e, "est_tokens": est_tokens(piece)}
        for i, (s, e, piece) in enumerate(raw)
    ]

    out = {
        "doc_id": docid, "source": args.input, "unit": args.unit,
        "size": args.size, "overlap": args.overlap, "chunks": chunks,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"wrote {len(chunks)} chunks for doc '{docid}' -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
