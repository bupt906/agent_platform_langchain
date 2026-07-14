# Sub-skill: Graph Visualization

After `graph.json` is assembled and validated (Phases 6–7), generate a
self-contained, interactive HTML viewer so the user can explore the graph
visually. This is the last phase and is optional — offer it, or run it when the
user wants to *see* the graph.

## Quick start

```bash
python src/agent_platform/skills/knowledge-graph-extraction/scripts/generate_viewer.py kg_output/graph.json --out kg_output/graph.html
```

The output is one self-contained HTML file (loads vis-network 9.x from CDN; works
offline once that script is cached). Open it in any modern browser.

## Language handling (important)

The viewer is **language-agnostic** and matches the graph's language automatically:

- `--lang auto` (default) detects the graph's dominant script and shows the UI in
  Chinese for CJK graphs, English otherwise. Force it with `--lang zh` or
  `--lang en`.
- Node/edge labels are whatever the graph contains — if extraction produced a
  Chinese graph (see the language-consistency rule in `SKILL.md` and
  `references/validation.md`), the visualization is Chinese end to end.
- Colours, shapes, and all layouts are assigned from the entity types actually
  present, so non-Latin type labels (e.g. `组织`, `人物`) get distinct colours and
  correct layouts — there is no English-only fallback.
- The page uses a CJK-aware font stack, so Chinese/Japanese/Korean text renders
  cleanly.

## Layout

- **Left sidebar (top)**: layout selector, search, type filter, action buttons.
- **Left sidebar (bottom) — knowledge preview panel**: a docked, always-visible
  panel at the bottom-left. Clicking any node or edge renders its details here:
  type chip, degree, confidence, aliases, provenance (`source_chunks`),
  description, evidence quote, and a clickable **connections list**. It has its
  own header with a **← back** button (navigation history) and a **✕ close**.
  Selecting something while the sidebar is collapsed auto-expands it so the
  preview is never invisible.
- **Canvas (right)**: the graph, with a live stats bar (visible/total nodes and
  edges), a hint line, a loading indicator, and a help overlay.

## Viewer features

- **7 layouts** via dropdown or the `V` key: force-directed (default), circular,
  type-arc, hub-spoke, concentric rings, grid, hierarchical.
- **Search**: `Ctrl/⌘+K` focuses the box; typing lists matches; **Enter jumps to
  the first match**; clicking a result focuses and previews that node.
- **Type filter that doubles as a legend** — each row shows the type colour, name,
  and count. Hovering a row reveals an **"only"** action that solos that type in
  one click.
- **Neighbourhood highlight (fixed)**: selecting a node dims everything except it
  and its neighbours — including **edge labels**, which are made fully transparent
  along with their dimmed edges (previously labels stayed bright and floated over
  the canvas). Labels on the highlighted neighbourhood are revealed and
  brightened, even when global edge labels are toggled off.
- **Isolate neighbourhood**: a button in the node preview hides everything except
  the selected node and its direct neighbours; press it again (or Esc / ✕) to
  restore. Restoring re-applies the type-filter checkboxes exactly.
- **Navigation history**: walking the graph through the connections list builds a
  history; **← back** (or the `B` key) retraces your steps.
- **Dense-graph auto-declutter**: graphs with more than 60 edges start with edge
  labels hidden (the toggle button reflects this); hover tooltips and
  selection-reveal still show labels where they matter.
- **Drag** nodes; **Lock** (`L`) freezes positions; **Fit** (`F`); double-click a
  node to focus it; **double-click empty canvas to fit**.
- **Toggle edge labels**, **Export PNG**, **Help overlay** (`?`/`H`), **Reset all**
  (clears selection, isolation, history, filters, and label state).

## Technical notes (vis-network 9.x)

- `network.setPositions()` was removed in 9.x. Positions are set via
  `DataSet.update({id, x, y})` while `physics:false`, which is what the static
  layouts do.
- The five static layouts are precomputed in Python (`build_layouts()`) and
  embedded as `D.posCircular`, `D.posTypeCirc`, `D.posHub`, `D.posConc`,
  `D.posGrid`. Static layouts keep physics disabled so they don't collapse back
  to force-directed; re-enable physics by switching to the force view.
- Edge-label dimming is done by updating each edge's `font` (transparent colour,
  zero stroke) alongside its `color`/`width` — vis-network has no separate
  label-opacity control, so the font itself must be updated or labels stay bright.
- Graph data is embedded as a `D` object; `</` sequences in text are escaped so
  descriptions can't break out of the script tag, and the preview panel
  HTML-escapes all values.

## Customization

- Colours/shapes: `KNOWN_COLORS`, `KNOWN_SHAPES` (per-type overrides) and the
  `PALETTE` / `SHAPE_CYCLE` fallbacks in `scripts/generate_viewer.py`.
- Dense threshold: `DENSE = D.edges.length>60` in the embedded JS.
- Physics: `PN` in the embedded JS.
- Localization: add a language branch in `ui_strings()` and extend
  `resolve_lang()` if you need a UI beyond en/zh.

## Testing after generation

Open the HTML and confirm:

1. It loads with a force-directed layout in a couple of seconds (the loading
   spinner disappears when stabilized).
2. All 7 views switch without console errors, and edges are visibly connected.
3. Clicking a node fills the bottom-left knowledge preview and dims everything
   outside its neighbourhood — **including edge labels**; no bright labels should
   float over dimmed regions.
4. The connections list navigates on click and ← back retraces.
5. "Isolate neighbourhood" hides the rest of the graph and restores cleanly.
6. Type filters (and hover-"only") hide/show correctly; the stats bar updates.
7. For a non-English graph, labels and UI appear in the document's language.
8. For a graph with >60 edges, edge labels start hidden and the toggle button
   reads "Show edge labels" (or its localized equivalent).
