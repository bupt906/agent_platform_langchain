#!/usr/bin/env python3
"""
build_chunk_manifest.py - Build a global processing manifest from chunk files.

Deterministic (no LLM, no network). Standard library only.

Input files are JSON outputs from chunk_document.py:
  {
    "doc_id": "report2024",
    "source": "input.txt",
    "chunks": [
      {"id": "report2024.c0", "start_char": 0, ...}
    ]
  }

Usage:
    python scripts/build_chunk_manifest.py kg_output/chunks/ \
        --out kg_output/chunk_manifest.json
    python scripts/build_chunk_manifest.py a.chunks.json b.chunks.json \
        --out kg_output/chunk_manifest.json --artifact-dir kg_output/chunks
"""
import argparse
import glob
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone


def discover_inputs(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(sorted(glob.glob(os.path.join(path, "*.chunks.json"))))
        elif os.path.isfile(path):
            files.append(path)
        else:
            raise FileNotFoundError(path)
    return sorted(dict.fromkeys(files))


def default_artifact_dir(inputs, out_path):
    if len(inputs) == 1 and os.path.isdir(inputs[0]):
        return inputs[0]
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    return os.path.join(out_dir, "chunks")


def artifact_paths(artifact_dir, chunk_id):
    prefix = os.path.join(artifact_dir, chunk_id)
    return OrderedDict([
        ("schema_delta", prefix + ".schema_delta.json"),
        ("entities", prefix + ".entities.json"),
        ("relationships", prefix + ".relationships.json"),
        ("review", prefix + ".review.json"),
    ])


def load_chunk_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
        raise ValueError(f"{path} is not a chunk_document.py JSON file")
    return data


def build_manifest(input_files, artifact_dir):
    records = []
    for chunk_file in input_files:
        data = load_chunk_file(chunk_file)
        doc_id = data.get("doc_id") or os.path.splitext(os.path.basename(chunk_file))[0]
        chunks = data.get("chunks") or []
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("id") or f"{doc_id}.c{i}"
            prev_id = chunks[i - 1].get("id") if i > 0 else None
            next_id = chunks[i + 1].get("id") if i + 1 < len(chunks) else None
            records.append(OrderedDict([
                ("sequence", len(records)),
                ("doc_id", doc_id),
                ("chunk_id", chunk_id),
                ("chunk_file", chunk_file),
                ("source", data.get("source", "")),
                ("index_in_doc", i),
                ("prev_chunk_id", prev_id),
                ("next_chunk_id", next_id),
                ("start_char", chunk.get("start_char")),
                ("end_char", chunk.get("end_char")),
                ("est_tokens", chunk.get("est_tokens")),
                ("artifact_paths", artifact_paths(artifact_dir, chunk_id)),
                ("processing_status", "pending"),
            ]))

    for i, rec in enumerate(records):
        rec["global_prev_chunk_id"] = records[i - 1]["chunk_id"] if i > 0 else None
        rec["global_next_chunk_id"] = records[i + 1]["chunk_id"] if i + 1 < len(records) else None
    return records


def main():
    ap = argparse.ArgumentParser(description="Build a KG chunk processing manifest.")
    ap.add_argument("inputs", nargs="+",
                    help="Chunk JSON file(s) or directories containing *.chunks.json.")
    ap.add_argument("--out", required=True, help="Where to write chunk_manifest.json.")
    ap.add_argument("--artifact-dir", default=None,
                    help="Directory for per-chunk extraction artifacts "
                         "(default: input dir if input is a dir, else OUT_DIR/chunks).")
    args = ap.parse_args()

    try:
        input_files = discover_inputs(args.inputs)
        if not input_files:
            raise FileNotFoundError("no *.chunks.json files found")
        artifact_dir = args.artifact_dir or default_artifact_dir(args.inputs, args.out)
        chunks = build_manifest(input_files, artifact_dir)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    manifest = OrderedDict([
        ("metadata", OrderedDict([
            ("created", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("input_files", input_files),
            ("artifact_dir", artifact_dir),
            ("doc_count", len({c["doc_id"] for c in chunks})),
            ("chunk_count", len(chunks)),
        ])),
        ("chunks", chunks),
    ])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"wrote manifest for {len(chunks)} chunks -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
