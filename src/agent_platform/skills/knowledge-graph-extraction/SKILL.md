---
name: knowledge-graph-extraction
description: >-
  Extract a knowledge graph (entities and relationships) from one or more
  uploaded documents. Use this whenever the user wants to build, construct, or
  extract a knowledge graph, entity graph, concept map, or entity-relationship
  graph from documents, PDFs, reports, papers, notes, or raw text. Triggers
  include phrasings like "turn these docs into a graph", "pull out the entities
  and relationships", "map the concepts in this report", "build a KG from these
  files", "extract a graph of who-did-what", or "build an event-centric graph".
  Uses strict chunk-isolated,
  evidence-bearing schema seed/delta evolution and produces logically validated,
  schema-consistent graph files (JSON, GraphML, Cypher, RDF/Turtle). This skill
  is for knowledge-graph extraction and construction ONLY — not
  retrieval-augmented generation, embeddings, vector search, or question
  answering over the graph.
tools: [read_file, write_file, edit_file,bash]
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
| 1. Intake & parse | — | — |
| 2. Chunk inventory | — | `scripts/chunk_document.py`, `scripts/build_chunk_manifest.py` |
| 3. Schema seed/delta | `references/schema-design.md` | — |
| 4. Extract entities/events | `references/entity-extraction.md` | — |
| 5. Extract direct/event relations | `references/relationship-extraction.md` | — |
| 6. Validate local/global | `references/validation.md` | `scripts/validate_graph.py` |
| 7. Fuse, dedupe, emit | `references/output-formats.md` | `scripts/assemble_graph.py` |
| 8. Report/checkpoint | — | — |
| 9. Visualize (optional) | `references/visualization.md` | `scripts/generate_viewer.py` |

## Output contract

Create a working directory `kg_output/` (or honor a path the user gives). Final
deliverables go there:

- `graph.json` — the canonical graph (always produced). Schema in
  `references/output-formats.md`.
- `schema.json` — current ontology, updated only by applying the current chunk's
  approved delta to the previous schema version.
- `schema_seed.json` — immutable initial ontology, grounded only in allowed seed
  chunks (or marked `user_supplied`).
- `schema_history.json` — ordered seed/delta lineage and schema version history.
- `graph.graphml`, `graph.cypher`, `graph.ttl` — interchange formats, produced
  by `assemble_graph.py`.
- `validation_report.json` + `validation_report.md` — what was checked, what was
  fixed or dropped, and remaining warnings.
- `graph.html` — optional interactive viewer (Phase 9), when the user wants to
  explore the graph visually.

Intermediate state is part of the quality workflow, not throwaway scratch:

- `chunk_manifest.json` — ordered chunk inventory and expected artifact paths.
- `entity_index.json` — canonical entities seen so far, aliases, types,
  source chunks, descriptions, and open questions; event entries also track a
  compact signature of participants, time, place, trigger, sequence, and status.
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

## Non-negotiable streaming gate

Treat chunk ordering as an epistemic boundary, not a suggestion:

1. Parse and chunk the full source mechanically, but do not place the full text
   or future chunk texts in the schema/extraction model's context.
2. Infer `schema_seed.json` only from manifest records whose `index_in_doc` is
   `0` (the first chunk of each document and metadata physically inside it). This
   rule applies to short documents too.
3. Before completing chunk `ci`, do not open, read, search, summarize, or inspect
   any non-seed chunk `cj` whose manifest sequence is greater than `ci`.
4. Process one manifest chunk through schema check, delta application, extraction,
   local review, and `complete` status before opening the next chunk.
5. Write one evidence-bearing `schema_delta.json` per chunk. An empty delta is a
   positive fit decision and must contain the required `fit_check`; empty arrays
   alone are invalid.
6. Never replace `schema.json` with a freshly inferred whole-document schema.
   Its type set must equal the immutable seed plus additions/remaps recorded in
   processed deltas, in manifest order. Record every before/after version in
   `schema_history.json`.

Document length, heavy chunk overlap, expected equality with a one-shot final
schema, or efficiency are never waivers for this gate. They may make a delta
`no_change`; they do not permit precomputing the final schema or emitting
unexplained empty deltas.

If the host application automatically injects the whole document into the same
model context, stop and use an orchestration path that can pass one chunk packet
per call. Prompt wording cannot undo future-text leakage after the model has seen
the source.

## The pipeline

Operational order matters for every document size: run Phase 1 mechanically,
run Phase 2 to build the chunk manifest, create the immutable seed, then iterate
manifest chunks through Phases 3, 4, 5, 6, 7, and 8.

### Phase 1 — Intake & parse

Find the source documents (typically under `/mnt/user-data/uploads/` or a path
the user names) and convert each to plain text. For PDFs/DOCX/etc., use an
available parser. Keep this pass mechanical: write text to disk, record the
title/filename, detect parsing damage, and chunk it without asking the semantic
extraction model to interpret the whole source. If the same model would retain
the full text in context, perform parsing in a separate tool/process and begin
the semantic run from the manifest's seed chunk packet.

If parsing produces garbled text (OCR noise, broken tables), note it — quality
of extraction cannot exceed quality of parsing.

**Detect the dominant language of the documents now** and record it. Every later
phase writes generated text (type labels, descriptions, evidence paraphrases) in
this language. If a corpus is genuinely multilingual, pick the dominant language
for the schema vocabulary and keep each entity's description in the language of
the source that discusses it, but prefer one consistent language for type labels
so the schema stays coherent.

### Phase 2 — Chunk inventory

For anything longer than a few pages, split each document into overlapping
chunks so nothing is lost at boundaries:

```bash
python scripts/chunk_document.py <input.txt> --out kg_output/chunks/<docid>.chunks.json --size 600 --overlap 150
python scripts/build_chunk_manifest.py kg_output/chunks/ --out kg_output/chunk_manifest.json
```

Defaults (600-token-ish window, ~150 overlap) suit prose; widen for dense
reference material. Each chunk gets a stable id you will cite as provenance.
Short documents may produce one chunk, but still enter the manifest so the rest
of the pipeline has one consistent execution model.

The manifest is the driver for the rest of the work. Select one record
mechanically; do not load the complete `.chunks.json` into the semantic model.
For each chunk in order, load only:

- current chunk text,
- current `schema.json`,
- compact `entity_index.json`,
- relevant `unresolved_mentions.json` entries.

The current chunk already contains its configured overlap. Do not load the next
chunk during schema fit. After the current delta is applied, a short previous
chunk snippet may be loaded only when needed to resolve a named antecedent.

### Phase 3 — Schema seed and iterative deltas

A coherent graph needs a coherent schema, but it must never be inferred from a
whole-document prompt. Read `references/schema-design.md` after the manifest
exists and create `kg_output/schema_seed.json` only from manifest records whose
`index_in_doc` is `0`. For inferred schemas, every seed type must carry an exact
`evidence_quote` and `source_chunks`; mark supplied ontologies with
`schema_origin: user_supplied`. Once written, the seed is immutable.

Run Phase 3 inside every chunk cycle as a **schema fit check before extraction**:

1. Compare only the current chunk with the current generated `schema.json`.
2. Decide which asserted predicates remain direct relations and which qualified
   occurrences require event entity types plus event-role relationships.
3. Write `kg_output/chunks/<chunk_id>.schema_delta.json` with `fit_check`, exact
   evidence quotes, additions/remaps, and `schema_revision_before`.
4. Save the pre-change schema version, apply only this delta to a copy, update
   `schema.json`, and append a `schema_history.json` entry containing chunk id,
   before/after version, exact additions/remaps, and evidence.
5. Only then extract this chunk's entities and relationships. Record any schema
   addition/remap in `fusion_log.json` and re-check `affected_chunks`.

If the user supplied an ontology, store it as `schema_seed.json` with
`schema_origin: user_supplied`; record any extension request through deltas
instead of silently bending its types.

### Phase 4 — Extract entities and events per chunk (with gleaning)

Confirm the current delta has been applied and recorded, then read
`references/entity-extraction.md`. For the current chunk, identify entities
of the current schema types, including grounded event occurrences for types
marked `kind: event`. Use the global entity
index only to recognize already-known names, aliases, and safe cross-chunk
coreference; do not use it to invent entities absent from the chunk.

Prefer explicit event names. When an asserted event has no nominal name, use the
controlled event-label rule from the reference: combine only source-stated event
type/trigger, core participants, and stated time. Event nodes must exist here
before Phase 5 attaches role edges.

For every entity record: canonical `name`, `type`, `aliases`, a one–two sentence
`description` drawn from the text, the current `source_chunks`, and `confidence`.

Then **glean**: do one more focused pass asking "what real entities did I miss?"
Dense text routinely hides entities on the first read. Add only genuine misses;
do not pad.

Write results to `kg_output/chunks/<chunk_id>.entities.json`. If an entity-like
mention cannot be safely resolved, write it to `unresolved_mentions.json` rather
than creating a weak node.

### Phase 5 — Extract direct and event relationships per chunk (with gleaning)

Confirm the entity artifact exists, then read
`references/relationship-extraction.md`. Connect only entities available in
the current chunk context: current chunk entities plus safely resolved entities
from adjacent overlap or the entity index. The bar is high: **a relationship
must be asserted or unambiguously implied by text in the current context —
co-occurrence is not a relationship.**

Classify each predicate before writing edges. Keep stable two-party facts as
direct entity relations. Represent qualified occurrences as event entities with
event -> argument role edges for actors, affected objects, time, place, amount,
instrument, cause, and result; use event -> event edges for stated causal or
temporal links. Do not also persist the equivalent direct binary projection.

Record `source`, `target`, `type`, grounded `description`, short `evidence`,
`source_chunks`, and `confidence`. Glean once for missed relationships. Write
results to `kg_output/chunks/<chunk_id>.relationships.json`.

### Phase 6 — Validate local chunk, then global graph

This phase is why the graph can be trusted. Read `references/validation.md` and
apply it as **maximal rigor** in three loops:

- **Schema lineage gate:** verify that the seed cites only allowed seed chunks,
  each delta cites only its current chunk, every schema version equals the
  previous version plus that delta, and no final type lacks an introduction
  record. Treat a mismatch as a hard failure even if `graph.json` looks correct.

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
python scripts/validate_graph.py kg_output/graph.json --schema kg_output/schema.json --report kg_output/validation_report.json
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

For event fusion, compare event type, semantic participants, time, place,
sequence, trigger, and status. Merge compatible partial mentions and union their
roles/evidence; keep repeated or conflicting occurrences separate and audit the
decision.

At checkpoints and at the end, let the assembler canonicalize names, merge
duplicate entities, consolidate descriptions, deduplicate edges, and write every
output format:

```bash
python scripts/assemble_graph.py kg_output/chunks/ --schema kg_output/schema.json --aliases kg_output/aliases.json --out kg_output/graph.json --formats json,graphml,cypher,ttl --merge-report kg_output/merge_report.json
```

Merging is where most "logical" wins happen — "IBM", "I.B.M." and
"International Business Machines" must become one node so their edges converge.
Use the aliasing guidance and `entity_index.json` to feed the assembler a good
alias map; do not rely on string matching alone for non-obvious synonyms.

After assembly, loop back to Phase 6's structural validation. Review
`merge_report.json`; unresolved endpoints and duplicate candidates are work
items, not ignorable noise.

### Phase 8 — Report and checkpoint

After each artifact, advance `processing_status` by exactly one stage:
`pending → schema_checked → delta_applied → entities_extracted →
relationships_extracted → locally_reviewed → complete`. Never skip a stage and
never open the next chunk before the current one is `complete`. At the end, tell
the user briefly: entity and relationship
counts by type, chunk coverage, schema additions, fusion decisions, unresolved
mentions, conflicts found, low-confidence items kept, parsing problems, and
where the graph files live. Do not summarize the documents' contents — the graph
is the deliverable.

### Phase 9 — Visualize

If the user wants to *see* the graph, read `references/visualization.md` and
generate an interactive HTML viewer:

```bash
python3 scripts/generate_viewer.py kg_output/graph.json --out kg_output/graph.html
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
6. **Whole-document schema shortcut.** Parsing the whole file is not permission
   to infer from it. If future text entered the semantic model's context, discard
   the run and restart with isolated chunk packets.
7. **Untraceable schema replacement.** A final type absent from both the seed
   and ordered deltas invalidates the run, even if the final graph is plausible.
8. **Binary event collapse.** A qualified occurrence represented only as one
   actor-object edge loses participants, time, place, cause, and result. Reify the
   event when those dimensions matter, but do not duplicate it with a direct edge.

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
