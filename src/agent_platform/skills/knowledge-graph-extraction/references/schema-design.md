# Sub-skill: Schema Design

The schema (ontology) is the backbone of a logical graph. It is the list of
allowed **entity types** and **relationship types**, where each relationship
type declares which entity types it may connect. In the chunk-first workflow,
the schema starts as a small seed and then grows through deliberate per-chunk
deltas. This keeps extraction coherent without forcing late-document content
into an ontology inferred from an early, incomplete sample.

## Language of the schema

Write the type vocabulary in the documents' language. For a Chinese corpus the
entity types are e.g. `组织`, `人物`, `地点`, `产品` and the relationship types are
e.g. `创立`, `总部位于`, `开发` — not their English equivalents. The type labels are
the graph's schema, and the requirement is that the schema speaks the source
language. Keep the labels consistent (one language for the whole schema) even if
a few source passages are in another language.

## When to infer vs. when to load

- **User supplied an ontology/schema** → load it verbatim into `schema.json`,
  validate it has the fields below, and extract strictly against it. If the
  documents contain important things the schema can't express, surface that to
  the user rather than silently bending types.
- **No schema supplied (default)** → infer one from the documents, as below.

A neutral starting template lives at `assets/example_schema.json` — copy and
adapt it, but never extract against it verbatim: a schema that doesn't match the
corpus yields a graph that doesn't either.

## How to infer the seed schema

1. **Sample lightly.** Read the first manifest chunk of each document, headings
   or abstracts, and any obvious structural table. Do not read the whole long
   corpus just to infer the schema; that defeats the chunk-first workflow. You
   are looking for the *kinds* of things discussed, not every instance.

2. **Cluster into entity types.** Group the concrete things you see into a small
   set of types. Good types are mutually distinct and at a consistent level of
   abstraction. For a business corpus: `Person`, `Organization`, `Product`,
   `Location`, `Event`, `Financial_Metric`. For a scientific corpus: `Gene`,
   `Protein`, `Disease`, `Drug`, `Method`, `Dataset`. Aim for **5–15** types.
   Too few and everything collapses into `Concept`; too many and the schema is
   noise. Give each a one-line definition so extraction is unambiguous.

3. **Derive relationship types from real predicates.** Look at how the entities
   actually interact in the text and name those interactions specifically:
   `acquired`, `employed_by`, `located_in`, `treats`, `inhibits`, `cites`,
   `reports_to`, `subsidiary_of`. Prefer specific verbs over generic ones.
   Reserve a generic `related_to` only as a last resort and flag it for review —
   a graph full of `related_to` is a graph that failed to find the real
   relation. Aim for **8–20** relationship types.

4. **Constrain each relationship's endpoints.** For every relationship type,
   declare the allowed source and target entity types. `employed_by` is
   `Person -> Organization`; `subsidiary_of` is `Organization -> Organization`;
   `treats` is `Drug -> Disease`. These constraints are enforced later by the
   validator and catch a large class of nonsense edges (a `Disease` cannot
   `employ` a `Person`).

5. **Decide directionality conventions.** Fix a direction for each relationship
   and stick to it. `subsidiary_of` points from the smaller to the larger
   (`child -> parent`). Document it so extraction is consistent.

## schema.json format

```json
{
  "domain": "short label, e.g. 'corporate filings'",
  "entity_types": [
    { "type": "Person", "description": "A named individual human." },
    { "type": "Organization", "description": "A company, agency, or institution." }
  ],
  "relationship_types": [
    {
      "type": "employed_by",
      "description": "The person works or worked for the organization.",
      "source_types": ["Person"],
      "target_types": ["Organization"],
      "symmetric": false
    },
    {
      "type": "partnered_with",
      "description": "Two organizations in a stated partnership.",
      "source_types": ["Organization"],
      "target_types": ["Organization"],
      "symmetric": true
    }
  ]
}
```

- `symmetric: true` means direction doesn't matter (`partnered_with`,
  `co_authored_with`); the validator won't treat A→B and B→A as distinct.
- Allowing multiple `source_types`/`target_types` is fine when a relation
  genuinely spans them (e.g. `located_in: [Person, Organization] -> Location`).

## Per-chunk schema fit check

At the start of each chunk cycle, compare the current chunk against
`kg_output/schema.json` before extracting entities and relationships:

1. **Fits existing schema** -> write an empty `schema_delta.json` and continue.
2. **Important new entity kind** -> propose one new entity type with a short
   definition and examples from the chunk.
3. **Important new predicate** -> propose one relationship type with endpoint
   constraints, direction, and whether it is symmetric.
4. **Existing type is too broad or wrong** -> propose a remap or split, but only
   if the current schema would otherwise cause repeated mistyping.

Do not create a new type for a one-off mention that can be dropped. Do not
create a relationship type just because two entities co-occur. Schema growth is
for repeated or central facts the graph must express.

## schema_delta.json format

Each chunk writes `kg_output/chunks/<chunk_id>.schema_delta.json`. Use an empty
delta when no change is needed:

```json
{
  "chunk_id": "doc1.c3",
  "entity_types_add": [
    {
      "type": "Dataset",
      "description": "A named dataset or benchmark discussed in the source.",
      "evidence": "The chunk names the ImageNet validation set."
    }
  ],
  "relationship_types_add": [
    {
      "type": "evaluated_on",
      "description": "A method or model is evaluated on a dataset.",
      "source_types": ["Method", "Product"],
      "target_types": ["Dataset"],
      "symmetric": false,
      "evidence": "Model X was evaluated on ImageNet."
    }
  ],
  "remaps": [
    {
      "from": "related_to",
      "to": "evaluated_on",
      "reason": "The chunk repeatedly states evaluation predicates."
    }
  ],
  "affected_chunks": ["doc1.c1", "doc1.c2"]
}
```

`affected_chunks` lists earlier chunks, unresolved mentions, or relationship
records that should be rechecked after the delta is merged. If you add a schema
slot that could rescue previously unresolved content, mark it here and note the
decision in `kg_output/fusion_log.json`.

## Refining the schema during extraction

Schema design is a first pass, not a contract carved in stone. If, partway
through extraction, you hit an important entity or relation the schema can't
hold:

1. Pause. Decide whether it's genuinely a new type or a stray you should drop.
2. If genuine, **add a typed slot** (new entity type, or new relationship type
   with proper endpoint constraints) through the current chunk's
   `schema_delta.json`.
3. Update `schema.json` only after reviewing the delta for overlap with existing
   types.
4. Record the decision in `fusion_log.json` as `schema_add`, `schema_remap`, or
   `schema_reject`.
5. Re-check affected chunks and unresolved mentions before final assembly.

Never resolve the gap by mistyping the entity or using `related_to`.

A schema that grew deliberately by two types is healthy; a schema bypassed by ad
hoc edges is not.

## Schema checkpoints

For medium and large corpora, stop after every few chunks or after any schema
delta that changes endpoint constraints. Check that:

- entity types remain at a consistent abstraction level,
- relationship types are specific but not duplicates,
- new types are reflected in entity extraction and relationship extraction,
- old chunk outputs affected by the delta have been rechecked,
- `conflicts.json` records any type conflict that cannot be cleanly resolved.
