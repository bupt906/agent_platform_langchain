# Sub-skill: Relationship Extraction

This is where graphs most often go wrong, and therefore where this skill earns
its keep. A relationship (edge) asserts that a specific, typed connection holds
between two entities. For event-rich text, do not force a multi-part occurrence
into one binary edge: represent the occurrence as an event entity and connect
its participants and qualifiers with typed role edges. The defining rule remains:

> **A relationship must be asserted or unambiguously implied by the text.
> Co-occurrence is not a relationship.** Two entities appearing in the same
> sentence, paragraph, or chunk tells you nothing on its own. The text must
> state or clearly entail *how* they connect.

If you can't point to the words that justify an edge, the edge does not exist.

## Contents

- Mandatory precondition
- Relationship validity checks
- Direct-edge versus event decision
- Event-role extraction
- Record format and language
- Extraction and gleaning
- Cross-chunk event fusion
- Conflicts and uncertainty
- Cross-chunk bridge edges
- Schema gaps
- Anti-patterns and output

## Mandatory precondition

Do not begin relationship extraction until the current chunk's delta has been
applied and its entity artifact exists, including any event entities needed by
the current chunk. If an asserted occurrence should be reified but its event
entity is missing, return to entity extraction before writing role edges. If an
important asserted predicate has no compatible relationship type, stop and
return to the current chunk's schema fit check. Do not invent an ad hoc edge
type, reuse a future type, or redesign the complete schema during relationship
extraction.

In the chunk-first workflow, "the text" means the current chunk plus the small
context packet supplied for that chunk: overlap already embedded in the current
chunk, already extracted entities for this chunk, the current schema, compact
entity index entries, and relevant unresolved mentions. Do not open the next
chunk for context or scan the whole document to justify a single edge.

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
   schema's convention. "A reports to B" is `reports_to: A -> B`, never B -> A.
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

## Choose a direct edge or an event structure

Classify each asserted predicate before writing any edge. Use exactly one
primary representation unless the user explicitly requests a derived projection.

Use a **direct entity-to-entity edge** when the statement is adequately expressed
as a stable property, classification, membership, location, ownership, or other
two-party fact. Examples include `part_of`, `headquartered_in`, `member_of`, and
`has_component`.

Create an **event entity plus role edges** when the text describes an occurrence,
action, transition, or incident and one or more of these apply:

- three or more meaningful arguments or roles attach to the same occurrence;
- time, place, amount, instrument, status, cause, result, or condition matters;
- later sentences refer back to "the incident", "the acquisition", or another
  event mention;
- multiple chunks contribute different participants or qualifiers to one event;
- the same participants can undergo the same event type repeatedly and the
  occurrences must remain distinguishable.

Do not reify every verb. "Acme is headquartered in Perth" is a direct relation.
"Acme acquired Beta in Perth on 3 March" is an acquisition event because the
date, place, participants, and later consequences belong to one occurrence.

### Event graph direction convention

Use **event -> argument** direction for every event-role edge. This makes role
queries consistent regardless of the source sentence's grammar:

- event -> actor/initiator,
- event -> affected object or counterparty,
- event -> time and location,
- event -> instrument, amount, cause, and result.

Use event -> event direction for causal and temporal links such as `caused`,
`triggered`, `preceded`, and `prevented`. Mark role types in the schema with
`relation_kind: event_role` and event-to-event types with
`relation_kind: event_relation`.

### No duplicate direct projection

When an acquisition is represented as an event with `acquirer` and
`acquired_company` role edges, do not also persist a direct `acquired` edge
between the two organizations. That duplicates one fact in two topologies and
causes conflicting updates later. A consumer may derive the direct projection
from the event roles when needed.

## Extract event roles systematically

For every event entity already present in the current chunk's entity artifact:

1. Locate the exact trigger or event-denoting phrase.
2. Determine actuality: occurred/ongoing, planned, cancelled, hypothetical,
   negated, or uncertain. Do not turn a negated or hypothetical event into an
   asserted occurrence. Preserve material status in the event description or in
   a schema-defined status role.
3. Extract core participant roles required by the event type. Use semantic roles,
   not sentence positions: passive voice does not reverse actor and object.
4. Extract grounded time, place, amount, instrument, cause, result, and condition
   roles only when they matter to the corpus and corresponding entities exist.
5. Extract event-to-event causal or temporal links only when the text states or
   unambiguously entails them.
6. Give every role edge its own evidence span. One sentence may support several
   edges, but each edge must be independently justified.

If a required role is not stated or cannot be resolved, keep the grounded event
only when it remains meaningful, add the missing role to
`unresolved_mentions.json`, and let validation flag the event as incomplete. Do
not invent a participant to make the event look complete.

### Event-centered example

```text
Source: On 3 March 2024, Acme acquired Beta in Perth for $2 billion.

Event entity: Acme acquisition of Beta (3 March 2024) [AcquisitionEvent]
Role edges:
- event -> Acme: acquirer
- event -> Beta: acquired_company
- event -> 3 March 2024: occurred_on
- event -> Perth: occurred_in
- event -> $2 billion: transaction_value

Do not also emit: Acme -> Beta: acquired
```

## Record format (per relationship)

```json
{
  "source": "IBM acquisition of Red Hat (2019)",
  "target": "International Business Machines",
  "type": "acquirer",
  "description": "IBM is the acquiring organization in this acquisition event.",
  "evidence": "IBM completed its acquisition of Red Hat.",
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
- **Event triggers and arguments.** "acquired", "exploded", "rescued",
  "appointed", and their nominal forms may introduce an event whose participants
  and qualifiers require separate role edges.

## Gleaning for relationships

After the first pass, re-scan asking: *which real relationships between
already-found entities did I miss?* Commonly missed:

- relationships stated across a sentence boundary or via a pronoun,
- multiple relationships packed into one dense sentence,
- relations expressed by nouns rather than verbs ("the IBM–Red Hat deal"),
- negative/temporal qualifiers ("formerly employed by") — capture these with the
  qualifier in the description, don't drop the edge for being past-tense.
- missed event entities, core participant roles, event time/place, and stated
  event-to-event causes or results.

Add only grounded relations. As with entities, an empty gleaning pass is fine.

## Cross-chunk event fusion

Treat event coreference as stricter than ordinary entity aliasing. Two mentions
refer to the same event only when their event types match and their available
identity dimensions are compatible:

- core participants and semantic roles,
- normalized or source-stated time,
- location,
- trigger/nominal mention,
- outcome or status.

Record these dimensions as an `event_signature` in the event's
`entity_index.json` entry. The signature is fusion evidence, not permission for
string-only merging. Merge partial mentions when later chunks add compatible
roles; union their evidence and `source_chunks`. Keep events separate when time,
place, sequence, or status distinguishes repeated occurrences, even if the same
participants and event type recur.

After approving a merge, reuse the existing canonical event name and add only
source-backed mentions as aliases. Update `aliases.json` when needed; the
assembler does not interpret `event_signature` or infer event identity itself.

If two mentions are probably the same event but the identity dimensions are too
sparse, keep them separate and write an unresolved event-coreference item. If
they disagree on time, participants, status, cause, or result, write the issue to
`conflicts.json` and record the merge/keep-both decision in `fusion_log.json`.

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

- the source and target are named across overlap embedded in the current chunk,
- the current chunk uses a pronoun whose antecedent is explicit in that embedded
  overlap,
- an acronym or alias is grounded in the current chunk's embedded overlap or
  already listed in `entity_index.json`,
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
- **Binary event collapse.** Do not reduce a qualified multi-part event to one
  actor-object edge and discard its time, place, cause, result, or other roles.
- **Event over-reification.** Do not create event nodes for every verb or stable
  attribute; event nodes must denote identifiable occurrences.
- **Dual representation.** Do not store both an event-role structure and its
  direct binary projection unless the schema explicitly declares the projection.
- **Role reversal.** Event-role edges always point from the event to its argument,
  including when the source sentence is passive.
- **Event conflation.** Do not merge repeated events merely because they share a
  type and participants; compare time, place, sequence, and status.

## Output

Write per-chunk relationships to
`kg_output/chunks/<chunk_id>.relationships.json`. If a relationship is dropped,
remapped, or kept despite a conflict, record that in the chunk's `.review.json`
and in `fusion_log.json`. Relationship endpoint names must match entity `name`
or known aliases so `assemble_graph.py` can resolve them.
