# Sub-skill: Validation (the Logical Gate)

This is the pass that lets the graph be trusted. Extraction proposes; validation
disposes. Run it as **maximal rigor**: examine every node and every edge, not a
sample. In the chunk-first workflow there are three gates: a local chunk review,
an incremental fusion review, and a final structural check
(`scripts/validate_graph.py`). Do all three; they catch different defects.

## Gate 1 — Local chunk review

For each chunk, re-read its `.entities.json` and `.relationships.json` against
the current chunk text, adjacent overlap used for coreference, current schema,
and relevant entity-index/unresolved records. The mindset is adversarial: try to
*disprove* each item. An item survives only if you can't.

Write `kg_output/chunks/<chunk_id>.review.json` with:

- dropped entities and relationships, with reasons,
- retyped entities or remapped relationships,
- unresolved mentions that need later evidence,
- schema delta needs,
- conflict candidates against earlier chunks,
- accepted warnings that should be visible in the final report.

### Review every entity

- **Real and grounded?** Can you find it in its `source_chunks`? If not, drop it.
- **Correctly typed?** Does its schema type actually fit? Retype or drop.
- **Canonical and merged?** Is this the same thing as another node under a
  different surface form? If clearly yes, merge (combine aliases, union
  `source_chunks`, keep the fuller description). If only maybe, leave separate
  and note it — wrong merges are worse than fragments.
- **Worth keeping?** Vague or incidental nodes that carry no edges and aren't
  meaningful subjects can be dropped to reduce noise.
- **Fusion-safe?** If it matches a prior entity, is the alias/coreference
  evidence strong enough? If not, keep separate and add an unresolved mention.

### Review every relationship

Apply the seven validity checks from `references/relationship-extraction.md` to
each edge: grounded, typed/in-schema, type-compatible, correctly directed,
specific, non-redundant, not over-inferred. For each edge, explicitly ask:

1. *Show me the evidence.* Is the `evidence` span real and does it support this
   exact relation? No → drop.
2. *Is this co-occurrence dressed up as a relation?* If the only justification is
   "they're mentioned together", drop it.
3. *Is the direction right?* Re-check source/target against the schema.
4. *Could a more specific relation replace a generic one?* Upgrade `related_to`
   to a real type, or drop it.
5. *Does this contradict another edge?* If so, go to conflict resolution.
6. *Does this need a schema delta?* If no relationship type fits, propose a
   schema change before forcing a bad relation.

### Language consistency

Confirm the graph speaks the documents' language: type labels, descriptions, and
evidence should be in the source language, while proper-noun names keep their
original form. The structural validator reports `language_mismatch` warnings for
descriptions or type labels whose script diverges from the graph's dominant
language (auto-detected, or set with `--lang zh|ja|ko|en|ru|ar`). Treat each flag
as a prompt to check: is this a legitimate proper noun (fine) or a fragment you
accidentally wrote/left in the wrong language (fix it)?

## Gate 2 — Incremental fusion review

After the local review, merge the chunk's clean items into the working state:
`entity_index.json`, `aliases.json`, `unresolved_mentions.json`,
`conflicts.json`, and `fusion_log.json`.

Review every fusion decision:

- **Merge:** same real entity under different grounded surface forms. Add
  aliases and source chunks; write a `merge` entry in `fusion_log.json`.
- **Split:** previously merged records are actually different entities. Remove
  the alias hint if needed and write a `split` entry.
- **Retype:** same entity should use a better schema type. Record previous type,
  new type, evidence, and affected chunks.
- **Relationship remap:** schema changed and an earlier edge now has a more
  precise type. Record the old and new type.
- **Keep both:** contradictory or time-scoped claims are both source-backed.
  Record why both remain.
- **Drop:** item fails grounding, schema, direction, or endpoint checks.

Never let a later chunk silently overwrite an earlier entity type, canonical
name, alias, or relationship. Every non-trivial fusion decision must be auditable
in `fusion_log.json`.

### Conflict resolution

When two edges (or an edge and an entity typing) genuinely contradict:

1. **Compare support.** Which is backed by clearer, more direct text? Prefer it.
2. **Compare confidence and provenance.** More sources, higher confidence wins,
   all else equal.
3. **Check for a temporal/qualified reconciliation.** "formerly employed_by" vs.
   "employed_by" aren't a contradiction — they're two time-scoped facts; keep
   both with qualifiers.
4. **If the source itself disagrees,** keep both edges and record the
   contradiction in the report rather than fabricating a resolution. The graph
   should reflect that the documents conflict.

Record open conflicts in `conflicts.json`, including conflict kind, competing
claims, source chunks, evidence, confidence, and current decision. Document every
drop, merge, retype, relationship remap, and conflict decision; Phase 8's report
and the validation report should make these auditable.

## Gate 3 — Structural validation (script)

After assembling `graph.json` (Phase 7), run:

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/validate_graph.py kg_output/graph.json --schema kg_output/schema.json --report kg_output/validation_report.json
```

It reports, split into **errors** (must fix) and **warnings** (review):

- **Dangling edge** (error): an edge whose `source` or `target` id is not a node.
  Usually a name that didn't resolve during assembly — fix the name or the merge.
- **Duplicate entity** (warning): two nodes with the same normalized name+type —
  candidates for merging.
- **Duplicate edge** (warning): same source/target/type more than once.
- **Schema violation — unknown type** (error): an entity or relationship type not
  in `schema.json`. Either it's a typo or the schema needs a deliberate addition.
- **Schema violation — incompatible endpoints** (error): e.g. a `treats` edge
  whose source isn't a `Drug`. Almost always a real logic bug — a mistyped entity
  or a wrong/reversed edge.
- **Self-loop** (warning): source == target. Occasionally valid; usually noise.
- **Orphan node** (warning): a node with no edges. Fine if it's a meaningful
  entity; consider dropping if it's incidental.

Treat every **error** as a must-fix and iterate: fix the underlying extraction or
schema, re-assemble, re-validate, until the error list is empty. Warnings are
judgment calls — resolve or consciously accept each, and let the report reflect
that.

Also review `kg_output/merge_report.json` after assembly. Unresolved endpoints,
alias misses, and duplicate candidates indicate incomplete fusion work even when
the structural validator can still produce a graph.

## When to stop

The graph is done when: the structural validator returns no errors; every
remaining warning has been reviewed and either resolved or knowingly accepted;
`conflicts.json` and `unresolved_mentions.json` contain only consciously accepted
items; and a spot-check of a handful of random edges shows each is genuinely
supported by its evidence. At that point the graph is small enough to be
wrong-free and rich enough to be useful — which is the goal.
