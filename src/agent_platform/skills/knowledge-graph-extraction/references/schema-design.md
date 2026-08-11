# Sub-skill: Schema Design

The schema is the typed ontology of the graph: allowed entity types and allowed
relationship types with endpoint constraints. Build it as an auditable sequence,
not as a one-shot summary of the corpus.

## Contents

- Hard read boundary
- Language and type quality
- Event-centered schema pattern
- Seed schema
- Per-chunk fit check
- Delta contract
- Applying a delta
- Schema checkpoints

## Hard read boundary

The semantic agent must not use the full document to infer the seed.

- A parser may read the full file mechanically to produce text and chunks.
- The semantic agent may initially read only the manifest's seed chunks: the
  first chunk of each document.
- A title, abstract, heading, or table may inform the seed only when its text is
  physically inside an allowed seed chunk.
- Before chunk `ci` is complete, do not open, search, summarize, or inspect a
  later non-seed chunk. This applies to short documents and one-page documents.
- Do not load the complete source or `.chunks.json` into the same model context.
  Select the current chunk mechanically and pass only its packet.
- The current chunk already contains configured overlap. Do not load the next
  chunk during schema fit.

If future text has already entered the model context, stop and restart the
semantic run with isolated chunk packets. Do not pretend to forget it.

## Language and type quality

Write schema vocabulary in the source language. Chinese sources use Chinese
type labels and descriptions; proper-noun names keep their source form.

Keep entity types mutually distinct and at a consistent abstraction level.
Prefer specific, text-grounded relationship predicates over `related_to`. Every
relationship type must declare `source_types`, `target_types`, direction, and
`symmetric`.

When the corpus is event-rich, distinguish schema roles explicitly:

- mark occurrence types with `kind: event`; ordinary entity types may use
  `kind: entity` or omit `kind` for backward compatibility;
- mark direct entity relations with `relation_kind: entity_relation`;
- mark event-to-argument roles with `relation_kind: event_role`;
- mark causal/temporal event-to-event links with
  `relation_kind: event_relation`.

All `event_role` edges use event -> argument direction. Do not mix event ->
argument and argument -> event conventions within one schema.

Do not create a type merely to make a delta non-empty. Add a type only when a
repeated or central kind/predicate cannot be represented correctly by the
current schema. Empty deltas are expected for chunks containing only new
instances of existing types.

## Event-centered schema pattern

Use event reification when one occurrence carries participants plus time, place,
status, amount, cause, result, or other qualifiers. Keep stable two-party facts
as direct relations. The graph remains a normal entity/relationship graph: an
event is an entity whose schema type has `kind: event`.

```json
{
  "entity_types": [
    { "type": "Organization", "description": "A named organization." },
    {
      "type": "AcquisitionEvent",
      "kind": "event",
      "description": "A specific acquisition occurrence.",
      "required_roles": ["acquirer", "acquired_company"]
    },
    { "type": "Time", "description": "A source-stated date or time interval." },
    { "type": "Location", "description": "A source-stated place." }
  ],
  "relationship_types": [
    {
      "type": "acquirer",
      "relation_kind": "event_role",
      "source_types": ["AcquisitionEvent"],
      "target_types": ["Organization"],
      "symmetric": false
    },
    {
      "type": "acquired_company",
      "relation_kind": "event_role",
      "source_types": ["AcquisitionEvent"],
      "target_types": ["Organization"],
      "symmetric": false
    },
    {
      "type": "occurred_on",
      "relation_kind": "event_role",
      "source_types": ["AcquisitionEvent"],
      "target_types": ["Time"],
      "symmetric": false
    },
    {
      "type": "caused",
      "relation_kind": "event_relation",
      "source_types": ["AcquisitionEvent"],
      "target_types": ["AcquisitionEvent"],
      "symmetric": false
    }
  ]
}
```

`required_roles` contains relationship type names needed to identify a minimally
useful instance of that event type. Keep it short and event-specific. Time,
location, amount, instrument, cause, and result are usually optional unless the
domain requires them. A missing required role is a review warning, not permission
to invent an argument.

Prefer semantic role labels such as `acquirer`, `acquired_company`, `rescuer`,
and `rescued_person` over syntactic labels such as `subject` and `object`. Do not
persist both an event-role structure and a direct entity-to-entity projection of
the same occurrence unless the user explicitly needs both and the schema marks
the projection as derived.

## Seed schema

Write the initial ontology to `kg_output/schema_seed.json`, then copy it to the
first `schema.json`. Never overwrite the seed.

For an inferred seed, require:

- `schema_origin: inferred`
- `schema_revision: 0`
- `seed_chunk_ids`: exactly the first manifest chunk of each document
- `domain`
- `entity_types`
- `relationship_types`

Every inferred seed entity type must contain:

- `type`
- `description`
- `evidence_quote`: an exact quote from an allowed seed chunk
- `source_chunks`: only allowed seed chunk ids

Every inferred seed relationship type must additionally contain non-empty
`source_types`, `target_types`, and boolean `symmetric`.

If the user supplied an ontology, preserve it as the immutable seed and set
`schema_origin: user_supplied`. User-supplied types do not need document
evidence, but later extensions still require current-chunk evidence.

Seed scope is a hard gate: a type unsupported by an allowed seed chunk must not
appear in the seed even if it is obvious from later text.

## Per-chunk fit check

At the start of every chunk cycle, before entity or relationship extraction:

1. Load only the current chunk packet and current `schema.json`.
2. List the important entity kinds in the chunk.
3. Map each kind to an existing entity type or mark it unmapped.
4. Identify important event kinds and decide whether they need reified event
   entities rather than direct edges.
5. List the important asserted predicates, event roles, and event-to-event links.
6. Map each predicate/role to an existing relationship type or mark it unmapped.
7. Decide whether the schema needs an addition or remap.
8. Write the delta before extracting entities or relationships.

Do not use a broad existing type merely to avoid a delta. Conversely, do not add
a narrow type for a one-off mention that can be dropped. The question is whether
the graph would repeatedly mistype or lose an important fact without the change.

## Delta contract

Write exactly one
`kg_output/chunks/<chunk_id>.schema_delta.json` for every manifest chunk.

Every delta must contain:

- `chunk_id`
- `schema_revision_before`
- `decision`: `no_change`, `extend`, `remap`, or `extend_and_remap`
- `fit_check`
- `entity_types_add`
- `relationship_types_add`
- `remaps`
- `affected_chunks`

`fit_check` must contain:

- `summary`: a concrete explanation of the decision
- `important_entity_kinds`: each with current-text `mention`, `mapped_to`, and
  `reason`
- `important_predicates`: each with current-text `predicate`, `mapped_to`, and
  `reason`
- `unmapped_items`: each with current-text `mention`, `kind`, and `reason`

For an unmapped item that causes an addition, include the corresponding new type
and an exact `evidence_quote` from the current chunk. A new relationship type
must also include endpoint constraints and `symmetric`.

A new event entity type must include `kind: event` and may declare
`required_roles`. A new event-role or event-to-event relationship type must
include `relation_kind`; event roles must constrain their source to event types.

A remap must include `kind`, `from`, `to`, `reason`, and a current-chunk
`evidence_quote`. List earlier outputs needing reconsideration in
`affected_chunks`.

### Empty delta rule

An empty delta is a positive claim that the current schema fully fits the chunk.
It is valid only when:

- `decision` is `no_change`;
- all addition/remap arrays are empty;
- `unmapped_items` is empty;
- `fit_check` explicitly maps every important entity kind and predicate to an
  existing type with a reason.

Empty arrays without this fit evidence invalidate the chunk. Never create empty
deltas merely because the final schema was inferred earlier from the full text.

## Applying a delta

Apply deltas strictly in manifest order. For each chunk:

1. Save the current revision as `schema_revision_before`.
2. Review additions for overlap and endpoint correctness.
3. Apply only the current chunk's approved additions/remaps to the previous
   schema; never redesign the whole schema from scratch.
4. Increment `schema_revision` when the schema changes.
5. Append a `schema_history.json` entry containing chunk id, before/after
   revision, exact additions/remaps, evidence quotes, and affected chunks.
6. Confirm the invariant below before extraction:

   `current schema = immutable seed + approved deltas through current chunk`

7. Record the same change in `fusion_log.json` and re-check affected prior
   chunks or unresolved mentions.

Any type in `schema.json` that cannot be traced to the seed or a processed delta
is a hard failure. A plausible final graph does not excuse broken lineage.

## Schema checkpoints

After every chunk with a schema change, and periodically for stable chunks,
verify:

- the model had no access to unprocessed chunk text;
- seed types cite only seed chunks;
- delta evidence appears in the current chunk, not a future chunk;
- revision numbers are continuous;
- every final type has an introduction record;
- empty deltas contain complete fit evidence;
- entity types remain at a consistent abstraction level;
- relationship types are specific, non-duplicate, and endpoint-compatible;
- event types have stable identity criteria and minimal `required_roles`;
- event-role edges consistently use event -> argument direction;
- event structures do not duplicate equivalent direct binary edges;
- affected old outputs were rechecked;
- conflicts and rejected schema proposals are recorded rather than hidden.
