# Sub-skill: Entity Extraction

An entity is a real, identifiable thing the document is about — a person, an
organization, a place, a defined concept, a method, or an identifiable event
occurrence. Your job is to find the ones that matter and name them consistently.
Quality here compounds: clean entities make relationships and merging far easier.

The most important rule is **surface-form grounding**: entity names must come
from the text you are extracting from. Do not use domain knowledge, common sense,
or a "better" standard term to name an entity that the chunk itself does not
name.

## Contents

- Mandatory precondition
- What qualifies as an entity
- Event entities and naming
- Record format
- Prose and table handling
- Language, normalization, and aliasing
- Cross-chunk fusion and unresolved mentions
- Coordinated phrases, tables, and lists
- Gleaning, anti-patterns, and self-check
- Output

## Mandatory precondition

Do not begin entity extraction until the current chunk's schema fit check and
delta exist, the delta has been applied to `schema.json`, and the change is
recorded in `schema_history.json`. If an important candidate still does not fit
the applied schema, stop extraction and return to schema design; never continue
under a type inferred from future text or a silently replaced full schema.

In the chunk-first workflow, extract from the current chunk plus only the small
context packet supplied by the manifest: overlap already embedded in the current
chunk, the current schema, compact `entity_index.json`, and relevant unresolved
mentions. Do not open the next chunk to obtain more overlap. The entity index
helps recognize known aliases; it is not a license to add an entity that the
current chunk does not name or clearly refer to.

## What qualifies as an entity

A candidate is a good entity when **all** of these hold:

- **It is a thing, not a description.** "Acme Corp" yes; "a fast-growing company"
  no. "CYP2C9" yes; "an important enzyme" no.
- **It fits a schema type.** If it doesn't fit any type and isn't worth a new
  type, drop it.
- **It is grounded.** It is actually named in the chunk, or it is a clearly
  named entity referred to by a pronoun/coreference after its introduction. Do
  not infer it from outside knowledge.
- **Its name is text-backed.** The chosen `name` must appear in the cited
  `source_chunks` exactly or be directly assembled from explicit source surface
  forms. The controlled event-label rule below is the only case where several
  grounded fields may be combined into one canonical label. If you cannot point
  to the words that justify the name, drop the candidate or rename it to the
  source wording.
- **It is salient.** It matters to the document's content. Skip boilerplate
  (page numbers, "Figure 1", "the authors" generically, headers/footers) unless
  such a thing is genuinely a subject of discussion.
- **It has a stable identity.** You could point to it again later and know it's
  the same thing. Pronouns and one-off paraphrases are not entities; the thing
  they refer to is.

## Event entities and controlled naming

Extract an event as an entity during Phase 4 when the current schema marks its
type with `kind: event` and the chunk asserts an identifiable occurrence. Event
entities are required before Phase 5 can attach participant, time, place, cause,
result, and other role edges.

Prefer an explicit source name or nominal mention such as "the North Ridge mine
accident" or "the acquisition". When an event is expressed only by a predicate,
create a controlled canonical label from source-stated dimensions:

`<core participant> + <event type/trigger> + <core object> + <time if stated>`

For example, "On 3 March 2024, Acme acquired Beta" may yield
`Acme acquisition of Beta (3 March 2024)`. Every component must be present in the
chunk; do not add inferred dates, places, participants, outcomes, or domain terms.
This label is an identifier for a grounded occurrence, not a claim that the exact
phrase appeared verbatim.

An event candidate must satisfy all of these:

- the text asserts, plans, denies, cancels, or otherwise discusses one occurrence;
- its event type exists in the current schema;
- it can be distinguished by trigger plus available participants, time, place,
  sequence, or status;
- it will receive at least one grounded role edge, or it is explicitly named and
  central enough to remain meaningful while a role is unresolved.

Do not create one event node per verb token. Repeated mentions of the same
occurrence become aliases/evidence for one event. Repeated occurrences with
different time, place, sequence, or status remain separate even when they share
participants and type.

## Record format (per entity)

```json
{
  "name": "International Business Machines",
  "type": "Organization",
  "aliases": ["IBM", "I.B.M.", "Big Blue"],
  "description": "Multinational technology company; referenced as the acquirer in the 2024 deal.",
  "source_chunks": ["doc1.c3", "doc1.c7"],
  "confidence": 0.95
}
```

- **name** is the canonical source surface form. Pick the fullest form that
  actually appears in the source chunks. The only exception is a controlled
  event label assembled under the rule above. Do **not** replace a name with a
  more standard, more general, or more domain-familiar term absent from the text.
- **aliases** are other surface forms that appear in the source, plus safe
  punctuation/spacing/case variants. Do not put invented paraphrases or inferred
  names in `aliases`.
- **description** is one or two sentences, drawn from the text, that say what the
  entity is *in this corpus*. Keep it factual and grounded — it is not a place
  to add outside knowledge.
- **confidence** reflects how sure you are this is a real, correctly typed
  entity. Lower it for ambiguous mentions; the validator can filter on it.

Before writing a record, run this grounding check:

1. Can I find `name` in one of the cited `source_chunks`?
2. If not, can I find an alias that appears in the chunk and justifies this
   canonical name without adding outside knowledge?
3. For a reified event only, is every component of the controlled label explicitly
   stated in the cited chunk and tied to the same occurrence?
4. If not, the entity is not grounded enough. Drop it or use the source wording
   as `name`.

## Handle prose and tables separately during extraction

During entity extraction, first identify whether each passage in the chunk is
plain prose/headings or table-like content:

- **Plain prose and headings:** paragraphs, numbered clauses, section headings,
  definitions, and narrative text. Use the normal entity strategy in this file.
- **Tables and table-like text:** table titles, column headers, row groups,
  item rows, units, quantities, and OCR/PDF text that clearly came from a table.
  Use the table strategy below.

Do not mix the two modes casually. A row item from a table should not become a
free-floating entity just because it fits a schema type. Table-derived entities
should be extracted as part of a table hierarchy, so they have natural parent
nodes and relationships later.

## Language

Descriptions and the `type` label are written in the documents' language (a
Chinese document yields Chinese descriptions and Chinese type labels). The
`name`, however, is the surface form as it appears in the text: a proper noun
that appears in Latin script inside a Chinese document — "IBM", "OpenAI", a Latin
product code — stays in that form and is **not** translated. If the same entity
appears in two languages in the source (e.g. "鸿蒙操作系统" and "HarmonyOS"), pick
the dominant-language form as `name` and record the other as an alias.

## Normalization and aliasing (this drives good merging)

The same entity appears in many surface forms. Capture text-backed variants so
they collapse to one node:

- **Acronyms / expansions:** "WHO" ↔ "World Health Organization".
- **Abbreviated names:** "J. Smith", "Dr. Smith", "Jane Smith".
- **Punctuation/spacing/case variants:** "I.B.M." ↔ "IBM".
- **Honorifics/titles stripped:** canonical name without "Dr.", "Inc." kept only
  if it's part of the legal name and used consistently.
- **Coreference:** resolve "the company", "it", "the firm" to the named entity
  they point to within the chunk, and attribute facts to that named entity — but
  do **not** create an entity called "the company".

Normalization is for merging source mentions, not for inventing cleaner names.
If the source says "submersible pump", do not rename it to "high-lift pump"
unless "high-lift pump" is also a source surface form for the same entity.

When two surface forms might be the same entity but you're not sure (two people
named "Smith"; "Apple" the company vs. the fruit), **keep them separate** and
note the ambiguity rather than merging on a guess. Wrong merges create false
edges; missed merges only fragment, which is the safer error.

## Cross-chunk entity fusion

After each chunk, compare extracted entities with `kg_output/entity_index.json`:

- **Known entity, known alias:** use the existing canonical `name`, add the
  current surface form to `aliases`, and union `source_chunks`.
- **Known entity, new safe alias:** add the alias to the entity index and to
  `kg_output/aliases.json` so the assembler can force the same merge later.
- **Possible but uncertain match:** keep the chunk entity separate and add an
  `unresolved_mentions.json` entry with the candidate canonical names and the
  evidence that made it ambiguous.
- **Type conflict:** do not overwrite the existing type. Add a conflict entry
  with both candidate types, supporting chunks, and the decision needed.

For event entities, also maintain an `event_signature` in the entity index with
the available event type, trigger/nominal mentions, semantic participants, time,
location, sequence, and status. Merge event mentions only when these dimensions
are compatible. Sparse but plausible matches belong in `unresolved_mentions.json`;
conflicting or repeated occurrences stay separate.

Only record an alias when the source backs it: acronym expansion, repeated
surface forms, appositive naming, or unambiguous adjacent/coreference context.
Do not merge merely because names are similar.

## Pronouns and unresolved mentions

Resolve pronouns and generic references only when the antecedent is explicit in
the same chunk or in the adjacent overlap supplied by the manifest. If the chunk
says "it", "the system", "the company", or an acronym whose expansion is not
available in the current context, do not create a new entity and do not guess.
Write a compact unresolved record instead:

```json
{
  "chunk_id": "doc1.c5",
  "mention": "the company",
  "candidate_entities": ["International Business Machines"],
  "reason": "The prior chunk discusses IBM, but this chunk alone does not name it.",
  "needed_evidence": "A nearby explicit name or alias that grounds the reference."
}
```

Later chunks may resolve the mention. When they do, update `entity_index.json`,
`aliases.json`, and `fusion_log.json`; keep the unresolved entry if the evidence
never becomes strong enough.

## Coordinated and compressed phrases

Documents often name multiple things in compressed forms. Keep the source wording
unless the text explicitly provides the expanded names.

- Do not create a singularized or partially expanded entity name that does not
  appear in the source.
- If a coordinated phrase names one document section, method, program, or event,
  keep that coordinated phrase as the entity name.
- You may extract component entities only when those component names are
  independently present or directly recoverable without changing the meaning.

Few-shot example:
```text
Source: response procedures for warehouse fires, chemical spills, and power outages
Good incident-type entities: warehouse fires; chemical spills; power outages
Bad inferred entity: chemical spill response team
Reason: the source names incident types and procedures here, not a separate team.
```

## Tables and lists

Tables, OCR output, and PDF-to-text conversion often separate column headers,
categories, item names, descriptions, units, and quantities across lines. If you
extract every visible cell as a standalone node, the graph will be full of
orphans. Instead, model tables as structured context.

For table-derived content, extract entities in this order:

1. **The prose anchor.** If nearby prose introduces the table or table range,
   keep the domain entity named by that prose. When the prose names a domain
   object and an explicit table range, you may create a source-backed aggregate
   name by combining both, such as `emergency equipment (Tables 1-5)`. Both
   parts must appear in the source.
2. **The table title.** Treat the whole table as an entity when its contents are
   central to the document, especially when prose points to it. Use the source
   title, such as `Table 1 Basic Emergency Equipment`.
3. **Row-group or category labels.** Keep labels such as equipment categories,
   requirement categories, or role groups only when they are meaningful domain
   containers and can be connected to the table entity.
4. **Individual row items.** Extract item-level entities only when the schema and
   the user's goal need that granularity **and** the item can be connected to a
   parent table/category. Otherwise, keep item details in the parent entity's
   description instead of creating more nodes.

Do not extract units, quantities, row numbers, blank cells, or measurement
requirements as standalone entities unless the schema explicitly models them.
These details belong in descriptions or relationship evidence.

The relationship extraction pass should then connect the hierarchy, for example:
document/prose entity -> table range aggregate -> table title -> row category ->
optional row item. This entity extraction step should provide the nodes needed
for that hierarchy, not a flat list of isolated cells.

Few-shot example:

```text
Source prose:
Response teams must maintain emergency equipment for incident response. Basic
equipment standards are listed in Tables 1-5.

Source table title:
Table 1 Basic Emergency Equipment

Source table text:
Category | Equipment name | Requirement | Unit | Quantity
Vehicles | command vehicle | emergency warning system | vehicle | 2
Vehicles | mobile lab | gas analyzer and printer | vehicle | 1
Communications | video command system | two-way video and audio | set | 1
Drainage equipment
submersible pump
flow rate of 100 m3/h or 200 m3/h
high-pressure drainage hose
pressure rating above 4.5 MPa

Good core entities:
- Response teams
- emergency equipment (Tables 1-5)
- Table 1 Basic Emergency Equipment
- Vehicles
- Communications
- Drainage equipment

Optional item-level entities, only if item-level equipment is needed and will be
connected to parent categories:
- command vehicle
- mobile lab
- video command system
- submersible pump
- high-pressure drainage hose

Expected hierarchy for relationship extraction:
- Response teams, maintain, emergency equipment (Tables 1-5)
- emergency equipment (Tables 1-5), includes, Table 1 Basic Emergency Equipment
- Table 1 Basic Emergency Equipment, includes, Vehicles
- Vehicles, includes, command vehicle

Bad equipment entity: high-lift pump
Reason: high-lift pump is domain-plausible, but it does not appear in the table.

Bad standalone entities:
- vehicle
- 2
- pressure rating above 4.5 MPa
- a flat list of table items with no table/category parent
```

## Gleaning (the second pass)

After the first pass, re-read the chunk asking specifically: *what real entities
did I miss?* First passes reliably skip:

- entities mentioned only in passing or inside a list,
- the second and third items of a coordinated phrase ("A, B, and C"),
- entities referred to only by pronoun after their introduction,
- quantitative or technical entities (metrics, genes, statutes, dates that name a
  specific event),
- event occurrences expressed by nominalizations or referred to across sentence
  boundaries after their trigger.

Add only genuine entities. Do not invent items to fill the pass — an empty
gleaning result is a fine result.

During gleaning, apply the same surface-form grounding check. Gleaning is for
missed source mentions, not for adding inferred domain concepts.

## Anti-patterns to avoid

- **Bare verbs and adjectives as entities.** "innovative" and an isolated
  "increased" are not entities. A grounded occurrence expressed by a verb may be
  reified only through the controlled event rule above.
- **Plausible but absent names.** "high-lift pump" is not a valid entity if the
  source only says "submersible pump" and "slurry pump".
- **Rewritten section titles.** Do not simplify or expand a source heading into a
  cleaner title that is not present in the source.
- **Whole clauses as entities.** "the decision to expand into Europe" may be an
  event worth modeling, but use a short label assembled only from source-stated
  dimensions; do not turn the complete clause into a node name or invent a
  polished title absent from the source.
- **Generic placeholders.** "the system", "the data", "the approach" with no
  specific referent. If a specific system/dataset/method is named, use that name.
- **Document-structure artifacts.** "Section 3", "Table 2", "the appendix" —
  unless the document itself is the subject (e.g. a corpus of papers that cite
  each other's tables) or the table is being modeled as a domain data container
  using the table strategy above.
- **Over-splitting.** "New York" and "New York City" in the same context are one
  node; don't keep both unless the text clearly distinguishes state from city.
- **Over-typing one mention into several entities.** A single named thing gets a
  single entity record, even if it plays several roles.
- **Table-header hallucination.** Do not combine a table category, a requirement,
  and a familiar domain term into a new entity name.
- **Flat table-cell extraction.** Do not extract every table cell as a separate
  entity unless those entities will be connected to the table/category hierarchy.

## Pre-output self-check

Before writing the per-chunk JSON, review every entity:

- `name` appears in `source_chunks`, or a source-present alias directly supports
  it.
- `aliases` are source-backed variants, not guesses.
- `description` says only what the chunk supports.
- The entity is not just a unit, quantity, blank cell, role placeholder, or
  generic category.
- Table-derived entities have a clear table/category parent path, or they are
  dropped/kept only in a parent description.
- Coordinated phrases have not been silently rewritten into absent names.
- Cross-chunk aliases and coreferences are backed by current or adjacent text,
  not by a plausible memory of the document.
- Event labels contain only source-stated identity dimensions, and repeated event
  mentions were compared by participants, time, place, sequence, and status.
- Ambiguous cross-chunk mentions are written to `unresolved_mentions.json`
  instead of becoming weak entities.
- Low-confidence, hard-to-ground candidates are dropped rather than kept for
  coverage.

## Output

Write per-chunk entity lists to `kg_output/chunks/<chunk_id>.entities.json` as a
JSON array of the record format above. Then update `entity_index.json`,
`aliases.json`, `unresolved_mentions.json`, and `conflicts.json` as needed. The
assembler reads the entity files plus relationship files to build the final
graph.
