---
name: knowledge-graph-extraction
description: >-
  Extract a knowledge graph (entities and relationships) from one or more
  uploaded documents. Use this whenever the user wants to build, construct, or
  extract a knowledge graph, entity graph, concept map, or entity-relationship
  graph from documents, PDFs, reports, papers, notes, or raw text. Triggers
  include phrasings like "turn these docs into a graph", "pull out the entities
  and relationships", "map the concepts in this report", "build a KG from these
  files", or "extract a graph of who-did-what". Produces logically validated,
  schema-consistent graph files (JSON, GraphML, Cypher, RDF/Turtle). This skill
  is for knowledge-graph extraction and construction ONLY — not
  retrieval-augmented generation, embeddings, vector search, or question
  answering over the graph.
tools: [read_file, write_file, bash]
---

# Knowledge Graph Extraction

Turn unstructured documents into a clean, **logically valid** knowledge graph:
a set of typed entities (nodes) and the relationships (edges) that genuinely
hold between them, grounded in the source text.

The single most important property of the output is **correctness of meaning**
without losing coverage in long documents. Process long sources chunk by chunk:
small local passes reduce missed details, while incremental fusion turns those
local facts into one coherent graph. A small graph where every node is real and
every edge is asserted is still better than a padded graph; the chunk workflow is
there to find more grounded facts, not to lower the bar.

**Speak the documents' language.** The graph must be in the same language as the
source. If the documents are in Chinese, then entity descriptions, relationship
descriptions, and the schema's type vocabulary (entity types and relationship
types) are all in Chinese; likewise for any other language. The one exception is
proper-noun **names**, which keep their form as they appear in the text — a
company written "IBM" or "OpenAI" inside a Chinese document stays "IBM", it is
not translated. Detect the language once at intake and hold to it throughout;
`scripts/validate_graph.py` flags drift.

This skill covers extraction only. It does not build a retriever, embed text, or
answer questions — stop once the validated graph files are written.

## How the work is divided

You (the agent) do the *judgment* — reading text and deciding what is an entity
and what is a relationship. The bundled **scripts** do the *mechanics* —
deterministic chunking, merging, format conversion, and structural validation —
so that work is fast and never hand-rolled. The **references/** files are
loadable sub-skills: read each one when you reach its phase rather than all at
once.

| Phase | Read this sub-skill | Run this script |
|-------|--------------------|-----------------|
| 1. Intake & parse | `references/pdf-parsing.md` | — |
| 2. Schema seed/delta | `references/schema-design.md` | — |
| 3. Chunk inventory | — | `scripts/chunk_document.py`, `scripts/build_chunk_manifest.py` |
| 4. Extract entities | `references/entity-extraction.md` | — |
| 5. Extract relationships | `references/relationship-extraction.md` | — |
| 6. Validate local/global | `references/validation.md` | `scripts/validate_graph.py` |
| 7. Fuse, dedupe, emit | `references/output-formats.md` | `scripts/assemble_graph.py` |
| 8. Report/checkpoint | — | — |
| 9. Visualize | `references/visualization.md` | `scripts/generate_viewer.py` |

## Output contract

Create a working directory `kg_output/` (or honor a path the user gives). Final
deliverables go there:

- `graph.json` — the canonical graph (always produced). Schema in
  `references/output-formats.md`.
- `schema.json` — the entity/relationship ontology used.
- `graph.graphml`, `graph.cypher`, `graph.ttl` — interchange formats, produced
  by `assemble_graph.py`.
- `validation_report.json` + `validation_report.md` — what was checked, what was
  fixed or dropped, and remaining warnings.
- `graph.html` — optional interactive viewer (Phase 9), when the user wants to
  explore the graph visually.

Intermediate state is part of the quality workflow, not throwaway scratch:

- `chunk_manifest.json` — ordered chunk inventory and expected artifact paths.
- `entity_index.json` — canonical entities seen so far, aliases, types,
  source chunks, descriptions, and open questions.
- `aliases.json` — explicit surface-form to canonical-name hints used by
  `assemble_graph.py --aliases`.
- `unresolved_mentions.json` — pronouns, acronyms, generic mentions, and
  possible cross-chunk references that were not safe to resolve yet.
- `conflicts.json` — entity typing conflicts, relationship contradictions, and
  temporal/qualified disagreements.
- `fusion_log.json` — merge, split, retype, keep-both, drop, schema-add, and
  relationship-remap decisions.
- `merge_report.json` — deterministic assembler report with alias hits, merged
  entities, unresolved endpoints, and duplicate candidates.
- `chunks/<chunk_id>.schema_delta.json`, `.entities.json`,
  `.relationships.json`, `.review.json` — per-chunk extraction and review files.

## The pipeline

Operational order matters for long documents: run Phase 1, run Phase 3 to build
the chunk manifest, then iterate manifest chunks through Phases 2, 4, 5, 6, 7,
and 8. Phase numbers stay stable because they describe responsibilities, not a
single linear call stack.

### Phase 1 — Intake & parse

Find the source documents (typically under `/mnt/user-data/uploads/` or a path
the user names). Read each into plain text. For PDFs/DOCX/etc., use whatever
file-reading capability is available in this environment (e.g. a `pdf` or
`file-reading` skill, or a document-parser MCP tool if one is connected — probe
for it with the available tool-search before assuming it is absent). Record each
document's title/filename; you will tag entities with the documents they came
from.

If parsing produces garbled text (OCR noise, broken tables), note it — quality
of extraction cannot exceed quality of parsing.

**Detect the dominant language of the documents now** and record it. Every later
phase writes generated text (type labels, descriptions, evidence paraphrases) in
this language. If a corpus is genuinely multilingual, pick the dominant language
for the schema vocabulary and keep each entity's description in the language of
the source that discusses it, but prefer one consistent language for type labels
so the schema stays coherent.

### Phase 2 — Schema seed and iterative deltas

A coherent graph needs a coherent schema, but for long documents the schema must
not be frozen from a whole-document prompt. Read `references/schema-design.md`
after the chunk manifest exists and create a **seed schema** from a small
representative sample: the first chunk of each document, headings/abstracts, and
obvious structural tables. Write it to `kg_output/schema.json`.

Then run Phase 2 again inside every chunk cycle as a **schema fit check**:

1. Does the current chunk contain important entities or predicates the schema
   cannot express?
2. If yes, write `kg_output/chunks/<chunk_id>.schema_delta.json` with only the
   necessary additions or remaps.
3. Merge approved deltas into `schema.json`, record the change in
   `fusion_log.json`, and mark affected unresolved mentions or earlier chunks
   for re-check.

If the user supplied an ontology, use it as the starting schema and record any
needed extension request instead of silently bending its types.

### Phase 3 — Chunk inventory

For anything longer than a few pages, split each document into overlapping
chunks so nothing is lost at boundaries:

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/chunk_document.py <input.txt> --out kg_output/chunks/<docid>.chunks.json --size 1200 --overlap 150
python src/agent_platform/skills/knowledge-graph-extraction/scripts/build_chunk_manifest.py kg_output/chunks/ --out kg_output/chunk_manifest.json
```

Defaults (1200-token-ish window, ~150 overlap) suit prose; widen for dense
reference material. Each chunk gets a stable id you will cite as provenance.
Short documents may produce one chunk, but still enter the manifest so the rest
of the pipeline has one consistent execution model.

The manifest is the driver for the rest of the work. For each chunk in order,
load only:

- current chunk text,
- previous and next chunk IDs/text snippets when needed for overlap/coreference,
- current `schema.json`,
- compact `entity_index.json`,
- relevant `unresolved_mentions.json` entries.

### Phase 4 — Extract entities per chunk (with gleaning)

Read `references/entity-extraction.md`. For the current chunk, identify entities
of the current schema types, grounded in the chunk text. Use the global entity
index only to recognize already-known names, aliases, and safe cross-chunk
coreference; do not use it to invent entities absent from the chunk.

For every entity record: canonical `name`, `type`, `aliases`, a one–two sentence
`description` drawn from the text, the current `source_chunks`, and `confidence`.

Then **glean**: do one more focused pass asking "what real entities did I miss?"
Dense text routinely hides entities on the first read. Add only genuine misses;
do not pad.

Write results to `kg_output/chunks/<chunk_id>.entities.json`. If an entity-like
mention cannot be safely resolved, write it to `unresolved_mentions.json` rather
than creating a weak node.

### Phase 5 — Extract relationships per chunk (with gleaning)

Read `references/relationship-extraction.md`. Connect only entities available in
the current chunk context: current chunk entities plus safely resolved entities
from adjacent overlap or the entity index. The bar is high: **a relationship
must be asserted or unambiguously implied by text in the current context —
co-occurrence is not a relationship.**

Record `source`, `target`, `type`, grounded `description`, short `evidence`,
`source_chunks`, and `confidence`. Glean once for missed relationships. Write
results to `kg_output/chunks/<chunk_id>.relationships.json`.

### Phase 6 — Validate local chunk, then global graph

This phase is why the graph can be trusted. Read `references/validation.md` and
apply it as **maximal rigor** in two loops:

- **Local gate per chunk:** re-examine that chunk's entities and relationships
  against the chunk text, schema, current entity index, and unresolved mentions.
  Write `kg_output/chunks/<chunk_id>.review.json` with drops, retypes,
  unresolved items, schema needs, and conflict candidates.
- **Global gate after assembly:** run structural validation on the assembled
  graph and review merge effects.

Resolve conflicts explicitly. Keep the better-supported claim, or keep both with
a noted contradiction if the source genuinely disagrees. Never silently overwrite
an earlier fact during fusion.

Then run the structural validator on the assembled graph (Phase 7 produces the
file; validation is iterative with it):

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/validate_graph.py kg_output/graph.json --schema kg_output/schema.json --report kg_output/validation_report.json
```

It catches dangling edges, orphan nodes, duplicate entities/edges, self-loops,
and schema violations (including type-incompatible edges). Treat every hard error
as a must-fix and re-run until clean.

### Phase 7 — Incremental fusion, dedupe, emit

Read `references/output-formats.md` for the canonical JSON schema. Combine all
clean per-chunk extractions seen so far, then incrementally update:

- `entity_index.json` for canonical entities and open questions,
- `aliases.json` for safe alias-to-canonical merges,
- `unresolved_mentions.json` for mentions still needing later evidence,
- `conflicts.json` for type/relation contradictions,
- `fusion_log.json` for every merge, split, retype, drop, keep-both, schema-add,
  or relationship-remap decision.

At checkpoints and at the end, let the assembler canonicalize names, merge
duplicate entities, consolidate descriptions, deduplicate edges, and write every
output format:

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/assemble_graph.py kg_output/chunks/ --schema kg_output/schema.json --aliases kg_output/aliases.json --out kg_output/graph.json --formats json,graphml,cypher,ttl --merge-report kg_output/merge_report.json
```

Merging is where most "logical" wins happen — "IBM", "I.B.M." and
"International Business Machines" must become one node so their edges converge.
Use the aliasing guidance and `entity_index.json` to feed the assembler a good
alias map; do not rely on string matching alone for non-obvious synonyms.

After assembly, loop back to Phase 6's structural validation. Review
`merge_report.json`; unresolved endpoints and duplicate candidates are work
items, not ignorable noise.

### Phase 8 — Report and checkpoint

After each chunk, update the processing status in `chunk_manifest.json` or the
chunk review note. At the end, tell the user briefly: entity and relationship
counts by type, chunk coverage, schema additions, fusion decisions, unresolved
mentions, conflicts found, low-confidence items kept, parsing problems, and
where the graph files live. Do not summarize the documents' contents — the graph
is the deliverable.

### Phase 9 — Visualize (optional)

If the user wants to *see* the graph, read `references/visualization.md` and
generate an interactive HTML viewer:

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/generate_viewer.py kg_output/graph.json --out kg_output/graph.html
```

The viewer is self-contained and language-aware — it auto-detects the graph's
language for its UI and renders any-language type labels with distinct colours.
Offer it after the graph is validated; it is not required for the core
deliverable.

## Common Pitfalls

1. **Relationship file naming.** The assembler looks for `*.relationships.json` files
   (not `*.relations.json`). If you name the file wrong, the assembler silently
   produces a graph with zero relationships. Always verify the count after assembly.
2. **Orphan nodes.** The validator flags entities with no edges as orphan warnings.
   Every entity you extract should participate in at least one relationship. If an
   entity is genuinely isolated (e.g. a top-level system with no decomposition), add
   the relationship that connects it; otherwise drop the entity.
3. **Assembler sees zero relationships.** Check: (a) file is named `*.relationships.json`,
   (b) both `source` and `target` fields match entity `name` fields exactly, (c) file
   is valid JSON in `kg_output/chunks/`.
4. **Schema frozen too early.** Long documents often introduce new types late.
   Use per-chunk `schema_delta.json`, then re-check affected unresolved mentions.
5. **Silent cross-chunk overwrite.** If a later chunk contradicts an earlier
   type or edge, write `conflicts.json` and `fusion_log.json`; do not replace it
   without an auditable decision.
6. **`aliases.json` format is `{surface_form: canonical_name}`, not the reverse.**
   The assembler's `hint_canonical(name)` looks up the surface form to get the
   canonical name. Writing `{canonical: [alias1, alias2]}` (canonical → aliases
   list) causes `AttributeError: 'list' object has no attribute 'lower'` because
   the returned list gets fed to `normalize()`. The correct format maps every
   variant surface string to its single canonical string:
   `{"IBM": "International Business Machines", "I.B.M.": "International Business Machines"}`.
   If you already used canonical names everywhere and have no surface-form
   collisions to resolve, pass an empty `{}` rather than the wrong shape.

## Domain-Specific Schema Patterns

- **Fault-diagnosis / FMEA documents:** see `references/fault-diagnosis-schema.md`
  for the component→failure→cause→indicator→effect chain pattern, with worked
  entity types (部件, 故障模式, 故障原因, 判定指标, 影响) and relationship types
  (包含, 故障表现, 可能原因, 判定阈值, 导致).


- **No RAG.** If the user then asks to *query* the graph or build retrieval over
  it, that is out of scope for this skill — say so and stop here.
- **Grounding over coverage.** Never invent entities or relationships to make the
  graph look richer. Every node and edge must trace to text.
- **Schema discipline.** If something important does not fit the schema, extend
  the schema deliberately (add a typed slot and note it) rather than forcing it
  into a wrong type or a generic `related_to`.
- **Provenance always.** Keep `source_chunks` on every node and edge; it is what
  makes validation and later trust possible.
- **Language matches the source.** Generated text is in the documents' language;
  only proper-noun names keep their original form. Don't translate a Chinese
  corpus into an English graph (or vice versa).
- **MCP is optional here.** Output is files. Only reach for MCP tools to *ingest*
  documents (a parser) or, if the user explicitly wants it, to *enrich* entities
  from an external source. Probe for such tools; never block on them.

## Scale guidance

- **Small (≤ ~10 pages):** one or a few manifest chunks; still use the same
  chunk cycle so state files stay consistent.
- **Medium:** process each manifest chunk through schema fit, extraction,
  local validation, and fusion; assemble/validate at checkpoints.
- **Large / many documents:** same as medium, with more frequent schema review
  checkpoints and explicit attention to cross-document entity merging.
