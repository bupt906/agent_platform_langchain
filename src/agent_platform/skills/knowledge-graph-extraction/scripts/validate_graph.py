#!/usr/bin/env python3
"""
validate_graph.py — Structural validation of a knowledge graph. Catches the
mechanical defects that undermine logical integrity: dangling edges, duplicate
nodes/edges, self-loops, orphan nodes, unknown types, and schema-incompatible
edge endpoints.

This complements (does not replace) the agent-level review in
references/validation.md. Run both.

Deterministic (no LLM, no network). Standard library only.

Also checks language consistency: descriptions and the schema's type vocabulary
should be in the documents' language (proper-noun names are exempt). Emits
`language_mismatch` warnings for drift; language is auto-detected or set with
--lang.

Usage:
    python validate_graph.py kg_output/graph.json
    python validate_graph.py kg_output/graph.json --schema kg_output/schema.json \
        --report kg_output/validation_report.json
    python validate_graph.py kg_output/graph.json --lang zh

Exit code is 1 if any ERROR-level issue is found, else 0 — so it can gate a
pipeline.
"""
import argparse
import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict


def norm(s):
    return " ".join((s or "").lower().replace(".", "").split())


# ── Language / script consistency ──────────────────────────────────
# The graph should speak the documents' language: entity/edge descriptions and
# the schema's type vocabulary should be in the source language (proper-noun
# NAMES may legitimately stay in their original script, so names are exempt).

_CONTENT_SCRIPTS = {"Han", "Kana", "Hangul", "Latin", "Cyrillic", "Arabic"}
LANG_TO_SCRIPT = {"zh": "Han", "ja": "Kana", "ko": "Hangul",
                  "en": "Latin", "ru": "Cyrillic", "ar": "Arabic"}


def _script_of_char(ch):
    if not ch.strip() or ch.isdigit():
        return None
    cp = ord(ch)
    if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
        return "Han"
    if 0x3040 <= cp <= 0x30FF:
        return "Kana"
    if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF:
        return "Hangul"
    if 0x0400 <= cp <= 0x04FF:
        return "Cyrillic"
    if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
        return "Arabic"
    try:
        if "LATIN" in unicodedata.name(ch):
            return "Latin"
    except ValueError:
        return None
    return None


def _script_profile(text):
    counts = {}
    for ch in text or "":
        fam = _script_of_char(ch)
        if fam:
            counts[fam] = counts.get(fam, 0) + 1
    return counts


def _dominant(counts):
    return max(counts, key=counts.get) if counts else None


def _expected_set(fam):
    # Treat CJK families together so Japanese (Han+Kana) / Korean (Hangul+Hanja)
    # mixing isn't mis-flagged.
    if fam in ("Han", "Kana"):
        return {"Han", "Kana"}
    if fam == "Hangul":
        return {"Hangul", "Han"}
    return {fam}


def language_check(graph, schema, lang_hint="auto", min_letters=4, share=0.6):
    """Flag descriptions and type labels whose dominant script differs from the
    graph's language. Names and evidence quotes are exempt. Returns warnings and
    the detected/expected language info."""
    # Determine the expected script family.
    if lang_hint != "auto" and lang_hint in LANG_TO_SCRIPT:
        expected = _expected_set(LANG_TO_SCRIPT[lang_hint])
        basis = lang_hint
    else:
        corpus = Counter()
        for e in graph.get("entities", []):
            corpus.update(_script_profile(e.get("description", "")))
        for r in graph.get("relationships", []):
            corpus.update(_script_profile(r.get("description", "")))
        for et in schema.get("entity_types", []):
            corpus.update(_script_profile(et.get("type", "")))
        for rt in schema.get("relationship_types", []):
            corpus.update(_script_profile(rt.get("type", "")))
        dom = _dominant(corpus)
        expected = _expected_set(dom) if dom else _CONTENT_SCRIPTS
        basis = "auto"

    warnings = []

    def check(text, where):
        prof = _script_profile(text)
        total = sum(prof.values())
        if total < min_letters:
            return
        dom = _dominant(prof)
        if dom in _CONTENT_SCRIPTS and dom not in expected \
                and prof[dom] / total >= share:
            warnings.append({
                "kind": "language_mismatch",
                "detail": (f"{where}: dominant script '{dom}' differs from graph "
                           f"language {sorted(expected)} — text: "
                           f"'{text[:50]}{'…' if len(text) > 50 else ''}'")})

    for et in schema.get("entity_types", []):
        check(et.get("type", ""), f"schema entity type '{et.get('type')}'")
    for rt in schema.get("relationship_types", []):
        check(rt.get("type", ""), f"schema relationship type '{rt.get('type')}'")
    for e in graph.get("entities", []):
        check(e.get("type", ""), f"{e.get('id')} type")
        check(e.get("description", ""), f"{e.get('id')} description")
    for r in graph.get("relationships", []):
        check(r.get("description", ""), f"{r.get('id')} description")

    info = {"basis": basis, "expected_scripts": sorted(expected)}
    return warnings, info


def load_schema(graph, schema_path):
    if schema_path and os.path.isfile(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return graph.get("schema") or {}


def build_type_rules(schema):
    entity_types = {et.get("type") for et in schema.get("entity_types", [])}
    rel_rules = {}
    for rt in schema.get("relationship_types", []):
        rel_rules[rt.get("type")] = {
            "source_types": set(rt.get("source_types") or []),
            "target_types": set(rt.get("target_types") or []),
            "symmetric": bool(rt.get("symmetric")),
        }
    return entity_types, rel_rules


def validate(graph, schema, lang_hint="auto"):
    errors, warnings = [], []
    lang_info = {}
    entities = graph.get("entities", [])
    rels = graph.get("relationships", [])

    by_id = {}
    for e in entities:
        eid = e.get("id")
        if not eid:
            errors.append({"kind": "missing_entity_id",
                           "detail": f"entity '{e.get('name')}' has no id"})
            continue
        if eid in by_id:
            errors.append({"kind": "duplicate_entity_id", "detail": eid})
        by_id[eid] = e

    entity_types, rel_rules = build_type_rules(schema)
    have_schema = bool(entity_types or rel_rules)

    # duplicate entities by normalized name + type
    seen = defaultdict(list)
    for e in entities:
        seen[(norm(e.get("name")), e.get("type"))].append(e.get("id"))
    for (nm, ty), ids in seen.items():
        if len(ids) > 1:
            warnings.append({"kind": "duplicate_entity",
                             "detail": f"{ids} share name/type ('{nm}', '{ty}') — merge?"})

    # unknown entity types
    if entity_types:
        for e in entities:
            if e.get("type") not in entity_types:
                errors.append({"kind": "unknown_entity_type",
                               "detail": f"{e.get('id')} has type '{e.get('type')}' not in schema"})

    # edges
    edge_seen = Counter()
    referenced = set()
    for r in rels:
        s, t, rt = r.get("source"), r.get("target"), r.get("type")
        rid = r.get("id", "?")

        if s not in by_id:
            errors.append({"kind": "dangling_edge",
                           "detail": f"{rid}: source '{s}' is not a node"})
        if t not in by_id:
            errors.append({"kind": "dangling_edge",
                           "detail": f"{rid}: target '{t}' is not a node"})
        if s in by_id:
            referenced.add(s)
        if t in by_id:
            referenced.add(t)

        if s == t:
            warnings.append({"kind": "self_loop",
                             "detail": f"{rid}: source == target ({s})"})

        sym = rel_rules.get(rt, {}).get("symmetric")
        key = (rt, frozenset((s, t))) if sym else (rt, s, t)
        edge_seen[key] += 1

        if have_schema:
            if rt not in rel_rules:
                errors.append({"kind": "unknown_relationship_type",
                               "detail": f"{rid}: type '{rt}' not in schema"})
            else:
                rule = rel_rules[rt]
                se, te = by_id.get(s), by_id.get(t)
                if se and rule["source_types"] and se.get("type") not in rule["source_types"]:
                    errors.append({"kind": "incompatible_endpoint",
                                   "detail": (f"{rid}: '{rt}' source is "
                                              f"{se.get('type')}, allowed "
                                              f"{sorted(rule['source_types'])}")})
                if te and rule["target_types"] and te.get("type") not in rule["target_types"]:
                    errors.append({"kind": "incompatible_endpoint",
                                   "detail": (f"{rid}: '{rt}' target is "
                                              f"{te.get('type')}, allowed "
                                              f"{sorted(rule['target_types'])}")})

    for key, c in edge_seen.items():
        if c > 1:
            warnings.append({"kind": "duplicate_edge",
                             "detail": f"{key} appears {c} times"})

    for e in entities:
        if e.get("id") not in referenced:
            warnings.append({"kind": "orphan_node",
                             "detail": f"{e.get('id')} ('{e.get('name')}') has no edges"})

    # language consistency (descriptions + schema/type vocabulary vs. graph language)
    lang_warnings, lang_info = language_check(graph, schema, lang_hint)
    warnings.extend(lang_warnings)

    return errors, warnings, lang_info


def render_md(graph, errors, warnings, schema_used, lang_info=None):
    ec = Counter(x["kind"] for x in errors)
    wc = Counter(x["kind"] for x in warnings)
    n_e = len(graph.get("entities", []))
    n_r = len(graph.get("relationships", []))
    lang_line = ""
    if lang_info:
        lang_line = (f"- Language: expected **{lang_info.get('expected_scripts')}** "
                     f"({lang_info.get('basis')})")
    lines = ["# Knowledge Graph Validation Report", "",
             f"- Entities: **{n_e}**", f"- Relationships: **{n_r}**",
             f"- Schema applied: **{'yes' if schema_used else 'no'}**"]
    if lang_line:
        lines.append(lang_line)
    lines += [f"- Errors: **{len(errors)}**  |  Warnings: **{len(warnings)}**", ""]
    if errors:
        lines += ["## Errors (must fix)", ""]
        lines += [f"- **{k}**: {v}" for k, v in ec.items()]
        lines += [""] + [f"  - {x['detail']}" for x in errors[:200]] + [""]
    else:
        lines += ["## Errors", "", "None — structurally clean.", ""]
    if warnings:
        lines += ["## Warnings (review)", ""]
        lines += [f"- **{k}**: {v}" for k, v in wc.items()]
        lines += [""] + [f"  - {x['detail']}" for x in warnings[:200]] + [""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Validate a knowledge graph.")
    ap.add_argument("graph", help="Path to graph.json")
    ap.add_argument("--schema", default=None,
                    help="schema.json (defaults to the schema embedded in graph.json)")
    ap.add_argument("--report", default=None,
                    help="Write JSON report here (and a .md sibling).")
    ap.add_argument("--lang", default="auto",
                    choices=["auto", "zh", "ja", "ko", "en", "ru", "ar"],
                    help="Expected language for consistency checks "
                         "(auto = infer from the graph's dominant script).")
    args = ap.parse_args()

    with open(args.graph, "r", encoding="utf-8") as f:
        graph = json.load(f)
    schema = load_schema(graph, args.schema)
    errors, warnings, lang_info = validate(graph, schema, args.lang)

    report = {
        "entity_count": len(graph.get("entities", [])),
        "relationship_count": len(graph.get("relationships", [])),
        "schema_applied": bool(schema.get("entity_types") or schema.get("relationship_types")),
        "language": lang_info,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }

    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        md_path = os.path.splitext(args.report)[0] + ".md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_md(graph, errors, warnings, report["schema_applied"], lang_info))
        print(f"report -> {args.report} and {md_path}")

    print(f"entities={report['entity_count']} relationships={report['relationship_count']} "
          f"errors={len(errors)} warnings={len(warnings)} "
          f"lang={lang_info.get('expected_scripts')}({lang_info.get('basis')})")
    for x in errors[:20]:
        print(f"  ERROR [{x['kind']}] {x['detail']}")
    for x in warnings[:20]:
        print(f"  warn  [{x['kind']}] {x['detail']}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
