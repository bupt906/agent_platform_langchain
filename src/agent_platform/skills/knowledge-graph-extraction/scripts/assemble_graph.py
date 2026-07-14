#!/usr/bin/env python3
"""
assemble_graph.py — Merge per-chunk extractions into one canonical knowledge
graph: deduplicate entities, assign stable ids, resolve relationship endpoints
from names to ids, deduplicate edges, and emit JSON + interchange formats.

Deterministic (no LLM, no network). Standard library only.

INPUT — either:
  * a directory containing  *.entities.json  and  *.relationships.json  files
    (each a JSON array of records), or
  * a single JSON file shaped like {"entities": [...], "relationships": [...]}.

Entity record  : {name, type, aliases?, description?, source_chunks?, confidence?}
Relationship   : {source, target, type, description?, evidence?, source_chunks?, confidence?}
                 (source/target are entity NAMES or aliases; resolved here to ids)

Usage:
    python assemble_graph.py kg_output/chunks/ --schema kg_output/schema.json \
        --out kg_output/graph.json --formats json,graphml,cypher,ttl
    python assemble_graph.py combined.json --out kg_output/graph.json

Options:
    --aliases path.json   Optional {"surface form": "Canonical Name"} hints to
                          force-merge non-obvious synonyms.
    --merge-report path   Optional JSON report of alias hits, merge groups,
                          unresolved endpoints, and duplicate candidates.
    --base-iri IRI        Base IRI for Turtle output (default http://example.org/kg/).
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

# ---------------------------------------------------------------- normalization

_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "professor", "sir", "the"}
_SUFFIXES = {"inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "co", "co.",
             "plc", "gmbh"}


def normalize(name):
    """Normalize a surface form for matching: lowercase, drop periods, strip
    honorifics/legal suffixes, collapse whitespace. Conservative on purpose —
    it should merge obvious variants without conflating distinct entities."""
    if not name:
        return ""
    s = name.lower().replace(".", "")
    s = re.sub(r"[^\w\s&-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [t for t in s.split(" ") if t]
    while toks and toks[0] in _HONORIFICS:
        toks = toks[1:]
    while toks and toks[-1] in _SUFFIXES:
        toks = toks[:-1]
    return " ".join(toks) if toks else s


# ------------------------------------------------------------------- load input

def load_records(path):
    entities, relationships = [], []
    if os.path.isdir(path):
        for fp in sorted(glob.glob(os.path.join(path, "*.entities.json"))):
            entities.extend(_read_array(fp))
        for fp in sorted(glob.glob(os.path.join(path, "*.relationships.json"))):
            relationships.extend(_read_array(fp))
        if not entities and not relationships:
            # maybe combined graph files live in the dir
            for fp in sorted(glob.glob(os.path.join(path, "*.json"))):
                e, r = _read_combined(fp)
                entities.extend(e)
                relationships.extend(r)
    elif os.path.isfile(path):
        e, r = _read_combined(path)
        entities, relationships = e, r
    else:
        raise FileNotFoundError(path)
    return entities, relationships


def _read_array(fp):
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("entities", data.get("relationships", []))


def _read_combined(fp):
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("entities", []), data.get("relationships", [])
    return [], []


# ---------------------------------------------------------------- entity merge

def merge_entities(records, alias_hints):
    """Merge entity records by (normalized name OR shared alias) + type.
    Returns ordered list of merged entities (without ids yet) and a
    resolution map  normalized_surface_form -> merged_index."""
    merged = []          # list of dicts
    key_to_idx = {}      # (norm, type) -> index
    alias_hint_hits = []

    def hint_canonical(name):
        return alias_hints.get(name) or alias_hints.get(normalize(name))

    for rec in records:
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        etype = (rec.get("type") or "Unknown").strip()
        canonical_hint = hint_canonical(name)
        if canonical_hint:
            alias_hint_hits.append(OrderedDict([
                ("surface", name),
                ("canonical", canonical_hint),
                ("type", etype),
                ("source_chunks", sorted(rec.get("source_chunks") or [])),
            ]))
        match_name = canonical_hint or name
        norm = normalize(match_name)
        key = (norm, etype)

        # also try matching via any alias already registered
        idx = key_to_idx.get(key)
        if idx is None:
            for al in rec.get("aliases", []) or []:
                k2 = (normalize(al), etype)
                if k2 in key_to_idx:
                    idx = key_to_idx[k2]
                    break

        if idx is None:
            entity = {
                "name": match_name,
                "type": etype,
                "aliases": set(a for a in (rec.get("aliases") or []) if a),
                "source_names": set([name]),
                "descriptions": [],
                "source_chunks": set(rec.get("source_chunks") or []),
                "confidence": float(rec.get("confidence", 0.5) or 0.5),
            }
            if name != match_name:
                entity["aliases"].add(name)
            if rec.get("description"):
                entity["descriptions"].append(
                    (entity["confidence"], rec["description"]))
            merged.append(entity)
            idx = len(merged) - 1
            key_to_idx[key] = idx
        else:
            entity = merged[idx]
            entity["source_names"].add(name)
            entity["aliases"].update(a for a in (rec.get("aliases") or []) if a)
            if name != entity["name"]:
                entity["aliases"].add(name)
            entity["source_chunks"].update(rec.get("source_chunks") or [])
            conf = float(rec.get("confidence", 0.5) or 0.5)
            entity["confidence"] = max(entity["confidence"], conf)
            if rec.get("description"):
                entity["descriptions"].append((conf, rec["description"]))
            # prefer the longest surface form as canonical name
            if len(match_name) > len(entity["name"]):
                entity["aliases"].add(entity["name"])
                entity["name"] = match_name
        # register this surface form for future resolution
        key_to_idx[(norm, etype)] = idx
        for al in rec.get("aliases", []) or []:
            key_to_idx[(normalize(al), etype)] = idx

    # finalize: ids, pick best description, register name+alias resolution map
    resolution = {}  # normalized surface -> id
    out = []
    entity_groups = []
    for i, e in enumerate(merged):
        eid = f"e{i+1}"
        best_desc = ""
        if e["descriptions"]:
            best_desc = max(e["descriptions"], key=lambda x: (x[0], len(x[1])))[1]
        aliases = sorted(a for a in e["aliases"] if a and a != e["name"])
        out.append(OrderedDict([
            ("id", eid),
            ("name", e["name"]),
            ("type", e["type"]),
            ("aliases", aliases),
            ("description", best_desc),
            ("source_chunks", sorted(e["source_chunks"])),
            ("confidence", round(e["confidence"], 3)),
        ]))
        resolution[normalize(e["name"])] = eid
        for al in aliases:
            resolution.setdefault(normalize(al), eid)
        entity_groups.append(OrderedDict([
            ("id", eid),
            ("name", e["name"]),
            ("type", e["type"]),
            ("source_names", sorted(e["source_names"])),
            ("aliases", aliases),
            ("source_chunks", sorted(e["source_chunks"])),
        ]))
    report = OrderedDict([
        ("alias_hint_hits", alias_hint_hits),
        ("entity_groups", entity_groups),
    ])
    return out, resolution, report


# ------------------------------------------------------------ relationship merge

def merge_relationships(records, resolution, symmetric_types, alias_hints=None):
    edges = OrderedDict()  # key -> edge dict
    unresolved = []
    alias_hints = alias_hints or {}
    alias_hint_hits = []

    def resolve_endpoint(name, role, rec):
        eid = resolution.get(normalize(name))
        if eid is not None:
            return eid
        canonical = alias_hints.get(name) or alias_hints.get(normalize(name))
        if not canonical:
            return None
        eid = resolution.get(normalize(canonical))
        if eid is not None:
            alias_hint_hits.append(OrderedDict([
                ("role", role),
                ("surface", name),
                ("canonical", canonical),
                ("type", rec.get("type", "")),
                ("source_chunks", sorted(rec.get("source_chunks") or [])),
            ]))
        return eid

    for rec in records:
        s_name = (rec.get("source") or "").strip()
        t_name = (rec.get("target") or "").strip()
        rtype = (rec.get("type") or "related_to").strip()
        if not s_name or not t_name:
            continue
        sid = resolve_endpoint(s_name, "source", rec)
        tid = resolve_endpoint(t_name, "target", rec)
        if sid is None or tid is None:
            missing = []
            if sid is None:
                missing.append("source")
            if tid is None:
                missing.append("target")
            unresolved.append(OrderedDict([
                ("source", s_name),
                ("target", t_name),
                ("type", rtype),
                ("missing", missing),
                ("source_chunks", sorted(rec.get("source_chunks") or [])),
            ]))
            # keep the raw name so the structural validator flags a dangling edge
            sid = sid or f"?{s_name}"
            tid = tid or f"?{t_name}"

        a, b = sid, tid
        if rtype in symmetric_types and a > b:
            a, b = b, a
        key = (a, b, rtype)
        conf = float(rec.get("confidence", 0.5) or 0.5)
        if key not in edges:
            edges[key] = {
                "source": a, "target": b, "type": rtype,
                "description": rec.get("description", "") or "",
                "evidence": rec.get("evidence", "") or "",
                "source_chunks": set(rec.get("source_chunks") or []),
                "confidence": conf,
            }
        else:
            ed = edges[key]
            ed["source_chunks"].update(rec.get("source_chunks") or [])
            ed["confidence"] = max(ed["confidence"], conf)
            if not ed["description"] and rec.get("description"):
                ed["description"] = rec["description"]
            if not ed["evidence"] and rec.get("evidence"):
                ed["evidence"] = rec["evidence"]

    out = []
    for i, (key, ed) in enumerate(edges.items()):
        out.append(OrderedDict([
            ("id", f"r{i+1}"),
            ("source", ed["source"]),
            ("target", ed["target"]),
            ("type", ed["type"]),
            ("description", ed["description"]),
            ("evidence", ed["evidence"]),
            ("source_chunks", sorted(ed["source_chunks"])),
            ("confidence", round(ed["confidence"], 3)),
        ]))
    report = OrderedDict([
        ("relationship_alias_hint_hits", alias_hint_hits),
    ])
    return out, unresolved, report


def duplicate_candidates(entities):
    by_norm = OrderedDict()
    for e in entities:
        key = normalize(e.get("name"))
        if not key:
            continue
        by_norm.setdefault(key, []).append(e)
    candidates = []
    for key, group in by_norm.items():
        if len(group) > 1:
            candidates.append(OrderedDict([
                ("normalized_name", key),
                ("entities", [
                    OrderedDict([
                        ("id", e.get("id")),
                        ("name", e.get("name")),
                        ("type", e.get("type")),
                        ("aliases", e.get("aliases", [])),
                        ("source_chunks", e.get("source_chunks", [])),
                    ])
                    for e in group
                ]),
            ]))
    return candidates


def write_merge_report(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------- emitters

def emit_graphml(graph):
    e_keys = {"name": "string", "type": "string", "description": "string",
              "confidence": "double"}
    r_keys = {"type": "string", "description": "string", "evidence": "string",
              "confidence": "double"}
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for k, t in e_keys.items():
        lines.append(f'  <key id="n_{k}" for="node" attr.name="{k}" attr.type="{t}"/>')
    for k, t in r_keys.items():
        lines.append(f'  <key id="e_{k}" for="edge" attr.name="{k}" attr.type="{t}"/>')
    lines.append('  <graph edgedefault="directed">')
    for n in graph["entities"]:
        lines.append(f'    <node id="{xml_escape(n["id"])}">')
        for k in e_keys:
            v = n.get(k, "")
            lines.append(f'      <data key="n_{k}">{xml_escape(str(v))}</data>')
        lines.append('    </node>')
    for e in graph["relationships"]:
        lines.append(f'    <edge id="{xml_escape(e["id"])}" '
                     f'source="{xml_escape(e["source"])}" '
                     f'target="{xml_escape(e["target"])}">')
        for k in r_keys:
            v = e.get(k, "")
            lines.append(f'      <data key="e_{k}">{xml_escape(str(v))}</data>')
        lines.append('    </edge>')
    lines.append('  </graph>')
    lines.append('</graphml>')
    return "\n".join(lines) + "\n"


def _cy_str(v):
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _rel_token(rtype):
    tok = re.sub(r"[^A-Za-z0-9_]", "_", rtype).strip("_").upper()
    return tok or "RELATED_TO"


def emit_cypher(graph):
    lines = ["// Knowledge graph — generated by assemble_graph.py",
             "// Load into Neo4j or a compatible property-graph store.\n"]
    for n in graph["entities"]:
        label = re.sub(r"[^A-Za-z0-9_]", "_", n["type"]).strip("_") or "Entity"
        props = (f"{{id: {_cy_str(n['id'])}, name: {_cy_str(n['name'])}, "
                 f"description: {_cy_str(n.get('description',''))}, "
                 f"confidence: {n.get('confidence',0)}}}")
        lines.append(f"CREATE (:{label} {props});")
    lines.append("")
    for e in graph["relationships"]:
        props = (f"{{description: {_cy_str(e.get('description',''))}, "
                 f"evidence: {_cy_str(e.get('evidence',''))}, "
                 f"confidence: {e.get('confidence',0)}}}")
        lines.append(
            f"MATCH (a {{id: {_cy_str(e['source'])}}}), "
            f"(b {{id: {_cy_str(e['target'])}}}) "
            f"CREATE (a)-[:{_rel_token(e['type'])} {props}]->(b);")
    return "\n".join(lines) + "\n"


def _ttl_str(v):
    s = (str(v).replace("\\", "\\\\").replace('"', '\\"')
         .replace("\n", "\\n").replace("\r", ""))
    return f'"{s}"'


def _ttl_local(token):
    tok = re.sub(r"[^A-Za-z0-9_]", "_", token).strip("_")
    if not tok:
        tok = "related_to"
    if tok[0].isdigit():
        tok = "_" + tok
    return tok


def emit_turtle(graph, base_iri):
    if not base_iri.endswith(("/", "#")):
        base_iri += "/"
    lines = [f"@prefix : <{base_iri}> .",
             "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
             "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", ""]
    for n in graph["entities"]:
        cls = _ttl_local(n["type"])
        triples = [f":{n['id']} rdf:type :{cls}",
                   f"rdfs:label {_ttl_str(n['name'])}"]
        if n.get("description"):
            triples.append(f":description {_ttl_str(n['description'])}")
        triples.append(f":confidence {n.get('confidence',0)}")
        lines.append(" ;\n    ".join(triples) + " .")
    lines.append("")
    for e in graph["relationships"]:
        lines.append(f":{e['source']} :{_ttl_local(e['type'])} :{e['target']} .")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Assemble a knowledge graph.")
    ap.add_argument("input", help="Chunks directory or a combined JSON file.")
    ap.add_argument("--out", required=True, help="Path for canonical graph.json.")
    ap.add_argument("--schema", default=None, help="schema.json (embedded + used).")
    ap.add_argument("--aliases", default=None, help="Optional alias-hints JSON.")
    ap.add_argument("--merge-report", default=None,
                    help="Optional JSON report of merges and unresolved endpoints.")
    ap.add_argument("--formats", default="json,graphml,cypher,ttl")
    ap.add_argument("--base-iri", default="http://example.org/kg/")
    args = ap.parse_args()

    schema = {}
    symmetric_types = set()
    if args.schema and os.path.isfile(args.schema):
        with open(args.schema, "r", encoding="utf-8") as f:
            schema = json.load(f)
        for rt in schema.get("relationship_types", []):
            if rt.get("symmetric"):
                symmetric_types.add(rt.get("type"))

    alias_hints = {}
    if args.aliases and os.path.isfile(args.aliases):
        with open(args.aliases, "r", encoding="utf-8") as f:
            alias_hints = json.load(f)

    ent_records, rel_records = load_records(args.input)
    entities, resolution, entity_report = merge_entities(ent_records, alias_hints)
    relationships, unresolved, relationship_report = merge_relationships(
        rel_records, resolution, symmetric_types, alias_hints)

    sources = sorted({c.split(".c")[0] for e in entities
                      for c in e["source_chunks"]})
    graph = OrderedDict([
        ("metadata", OrderedDict([
            ("source_documents", sources),
            ("created", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("schema_version", str(schema.get("schema_version", "1.0"))),
            ("stats", {"entity_count": len(entities),
                       "relationship_count": len(relationships)}),
        ])),
        ("schema", schema),
        ("entities", entities),
        ("relationships", relationships),
    ])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    stem = os.path.splitext(args.out)[0]
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    formats.add("json")  # canonical always

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    written = [args.out]
    if "graphml" in formats:
        p = stem + ".graphml"; open(p, "w", encoding="utf-8").write(emit_graphml(graph)); written.append(p)
    if "cypher" in formats:
        p = stem + ".cypher"; open(p, "w", encoding="utf-8").write(emit_cypher(graph)); written.append(p)
    if "ttl" in formats or "turtle" in formats:
        p = stem + ".ttl"; open(p, "w", encoding="utf-8").write(emit_turtle(graph, args.base_iri)); written.append(p)

    if args.merge_report:
        report_written = list(written) + [args.merge_report]
        report = OrderedDict([
            ("input", OrderedDict([
                ("entity_records", len(ent_records)),
                ("relationship_records", len(rel_records)),
            ])),
            ("output", OrderedDict([
                ("entity_count", len(entities)),
                ("relationship_count", len(relationships)),
                ("files_written", report_written),
            ])),
            ("alias_hint_hits", entity_report["alias_hint_hits"]),
            ("relationship_alias_hint_hits",
             relationship_report["relationship_alias_hint_hits"]),
            ("merged_entities", entity_report["entity_groups"]),
            ("unresolved_endpoints", unresolved),
            ("duplicate_candidates", duplicate_candidates(entities)),
        ])
        write_merge_report(args.merge_report, report)
        written.append(args.merge_report)

    print(f"entities: {len(entities)}  relationships: {len(relationships)}")
    if unresolved:
        print(f"WARNING: {len(unresolved)} relationship endpoint(s) did not "
              f"resolve to a known entity; structural validation will flag these "
              f"as dangling edges. Examples: {unresolved[:3]}", file=sys.stderr)
    print("wrote: " + ", ".join(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
