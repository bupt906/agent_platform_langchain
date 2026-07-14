# Sub-skill: Relationship Extraction

This is where graphs most often go wrong, and therefore where this skill earns
its keep. A relationship (edge) asserts that a specific, typed connection holds
between two entities. The defining rule:

> **A relationship must be asserted or unambiguously implied by the text.
> Co-occurrence is not a relationship.** Two entities appearing in the same
> sentence, paragraph, or chunk tells you nothing on its own. The text must
> state or clearly entail *how* they connect.

If you can't point to the words that justify an edge, the edge does not exist.

In the chunk-first workflow, "the text" means the current chunk plus the small
context packet supplied for that chunk: adjacent overlap, already extracted
entities for this chunk, the current schema, compact entity index entries, and
relevant unresolved mentions. Do not scan the whole document to justify a single
edge.

## What makes a relationship logically valid

Check every candidate edge against all of these. Failing any one means fix it or
drop it:

1. **Grounded.** There is specific text that asserts this connection. You can
   quote or tightly paraphrase it into the `evidence` field.
2. **Typed and in-schema.** The relation is one of the schema's relationship
   types — the *specific* one that fits, not a generic fallback.
3. **Type-compatible.** The source and target entity types are allowed for this
   relationship by the schema (`treats` needs `Drug -> Disease`; a `Person`
   cannot be the source of `treats`). If the types don't fit, either you picked
   the wrong relation, mistyped an entity, or the edge is wrong.
4. **Correctly directed.** Source and target are in the right order per the
   schema's convention. "A acquired B" is `acquired: A -> B`, never B -> A.
   Direction errors are common and silently corrupt the graph.
5. **Specific.** Prefer the most precise relation the text supports.
   "X reports to Y" → `reports_to`, not `related_to`. Generic edges carry almost
   no information and are usually a sign the real relation wasn't found.
6. **Non-redundant.** Not a duplicate of an existing edge, and not the trivial
   inverse of one already present (unless the schema models both directions
   deliberately).
7. **Not over-inferred.** Do not chain inferences the text doesn't make.
   "A works at B" and "B is in Paris" does **not** license "A located_in Paris"
   unless the text says so. Transitive and associative leaps are the main source
   of plausible-looking but false edges.

## Record format (per relationship)

```json
{
  "source": "International Business Machines",
  "target": "Red Hat",
  "type": "acquired",
  "description": "IBM acquired Red Hat in a deal described in the document.",
  "evidence": "IBM completed its acquisition of Red Hat for $34 billion.",
  "source_chunks": ["doc1.c3"],
  "confidence": 0.97
}
```

- `source`/`target` reference entities by their canonical `name` (the assembler
  resolves these to stable ids and will flag any that don't match a known
  entity).
- `evidence` is a short grounding span — a quote under ~15 words or a tight
  paraphrase. It is what makes the edge auditable in validation.
- `confidence` should drop when the relation is implied rather than stated, or
  when the entities involved were themselves low-confidence.

## Language

The relationship `type` and `description` are in the documents' language, matching
the schema's relationship vocabulary (e.g. `创立`, `收购` for a Chinese corpus, not
`founded`, `acquired`). The `evidence` span is a quote or tight paraphrase from the
source, so it is naturally in the source language too. Do not translate the graph
into a different language than the documents.

## How to extract relationships well

Work **within the entity set you already extracted** for the chunk. For each pair
of entities that the text actually discusses together, ask: *does the text say
how they relate?* If yes and it fits a schema type, record it. If the text only
places them near each other, record nothing.

The current entity set may include a previously known entity only when the chunk
or adjacent overlap clearly refers to it. If a relationship endpoint is a vague
pronoun or generic mention and the antecedent is not grounded, do not create the
edge; write an unresolved mention for later fusion.

Useful sources of real relationships:

- **Explicit predicates.** "X acquired Y", "X is headquartered in Y", "X inhibits
  Y" — the verb names the relation.
- **Appositives and definitions.** "Jane Smith, CEO of Acme, ..." gives
  `Smith employed_by Acme` (or a `has_role` relation if the schema models roles).
- **Stated causation/dependency.** "B was caused by A", "B requires A".
- **Membership/part-of.** "the Marketing team within Acme", "a module of the
  system".

## Gleaning for relationships

After the first pass, re-scan asking: *which real relationships between
already-found entities did I miss?* Commonly missed:

- relationships stated across a sentence boundary or via a pronoun,
- multiple relationships packed into one dense sentence,
- relations expressed by nouns rather than verbs ("the IBM–Red Hat deal"),
- negative/temporal qualifiers ("formerly employed by") — capture these with the
  qualifier in the description, don't drop the edge for being past-tense.

Add only grounded relations. As with entities, an empty gleaning pass is fine.

## Handling conflicts and uncertainty

- **Contradictions in the source.** If one chunk says "A subsidiary_of B" and
  another says "A subsidiary_of C", don't silently pick one. Keep the
  better-supported edge, or keep both and flag the contradiction in the report so
  the validator and the user can see it.
- **Cross-chunk contradictions.** Compare each new edge against the current
  fused graph or `entity_index.json`. If source, target, relation, or qualifier
  conflicts with an earlier chunk, write `conflicts.json` and record the decision
  in `fusion_log.json` as `keep_new`, `keep_existing`, `keep_both`, `drop_new`,
  or `temporal_qualification`.
- **Implied but unstated.** If a relation is strongly implied but not stated,
  you may include it at reduced confidence with the inference noted in
  `description`. If it's only a guess, leave it out.
- **Hedged claims.** "X may acquire Y", "reportedly partnered with" — keep the
  hedge in the description and lower confidence; don't present a possibility as a
  fact.

## Cross-chunk bridge edges

A relationship may bridge chunk boundaries only when the evidence packet makes
the bridge explicit:

- the source and target are named across adjacent overlap,
- the current chunk uses a pronoun whose antecedent is explicit in the adjacent
  overlap,
- an acronym or alias is grounded in the current/adjacent context or already
  listed in `entity_index.json`,
- the evidence field cites the chunk(s) that make the bridge auditable.

Do not bridge from distant document memory. If the likely endpoint appears only
far earlier and the current chunk does not name or clearly refer to it, write an
unresolved mention instead of an edge.

## Schema gaps during relationship extraction

If the chunk clearly states a relationship but no schema type fits, stop and
write a `schema_delta.json` proposal before forcing the edge. After the delta is
approved and merged into `schema.json`, re-extract or remap the affected
relationship and record the decision in `fusion_log.json`.

## Anti-patterns to avoid

- **Co-occurrence edges.** The single biggest mistake. Same sentence ≠ related.
- **`related_to` soup.** A graph where most edges are generic is a failed
  extraction; go back and find the real relations or drop the edges.
- **Reversed direction.** Re-check source/target against the schema convention.
- **Inverse duplicates.** Don't add both `parent_of` and `child_of` for the same
  pair unless the schema intends it.
- **Inference chains.** Don't synthesize edges the text never states by
  transitivity or association.
- **Entity-less edges.** Both endpoints must be real entities from the entity
  set; don't relate an entity to a vague phrase.

## Output

Write per-chunk relationships to
`kg_output/chunks/<chunk_id>.relationships.json`. If a relationship is dropped,
remapped, or kept despite a conflict, record that in the chunk's `.review.json`
and in `fusion_log.json`. Relationship endpoint names must match entity `name`
or known aliases so `assemble_graph.py` can resolve them.
