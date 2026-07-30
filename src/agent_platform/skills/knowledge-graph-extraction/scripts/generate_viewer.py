#!/usr/bin/env python3
"""Generate an interactive HTML knowledge-graph viewer from graph.json.

Usage:
    python3 generate_viewer.py graph.json [--out graph.html] [--lang auto|zh|en]

The output HTML is self-contained (loads vis-network 9.x from CDN); no runtime
dependencies. It is language-agnostic: colours, shapes, and layouts are assigned
from the entity types actually present, so a Chinese (or any-language) schema
renders exactly as well as an English one. With --lang auto (default) the UI
language follows the graph's dominant script.
"""

import argparse
import json
import math
import os
import sys
import unicodedata

# ── Palettes (used for ANY type label, in any language) ────────────
# Known English types keep their historical colour for continuity; every other
# type — including non-Latin labels like "组织" or "人物" — is assigned a stable
# colour/shape from these cycles, so the viewer never falls back to all-grey.
KNOWN_COLORS = {
    'Organization': '#4C72B0', 'Person': '#DD8452', 'Document': '#55A868',
    'Task': '#C44E52', 'Equipment': '#8172B2', 'Qualification': '#937860',
    'Event': '#CCB974', 'Standard': '#64B5CD', 'Location': '#8C8C8C',
    'Concept': '#B07AA1', 'Product': '#59A14F',
}
KNOWN_SHAPES = {
    'Organization': 'dot', 'Person': 'triangle', 'Document': 'square',
    'Task': 'star', 'Equipment': 'diamond', 'Qualification': 'hexagon',
    'Location': 'dot', 'Event': 'triangleDown', 'Product': 'square',
}
PALETTE = ['#4C72B0', '#DD8452', '#55A868', '#C44E52', '#8172B2', '#937860',
           '#CCB974', '#64B5CD', '#B07AA1', '#59A14F', '#EDC948', '#E15759',
           '#76B7B2', '#FF9DA7', '#9C755F', '#BAB0AC']
SHAPE_CYCLE = ['dot', 'triangle', 'square', 'diamond', 'star', 'hexagon',
               'triangleDown']

# Minimum empty space between rendered node boundaries in precomputed layouts.
# It is separate from visual size so the historical degree-based sizing stays
# unchanged.
NODE_GAP = 32
LEVEL_GAP = 110
COMPONENT_GAP = 180


# ── Small helpers ──────────────────────────────────────────────────

def _esc_html(s):
    """Escape for safe insertion into HTML attributes / tooltips."""
    if not isinstance(s, str):
        s = str(s)
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;'))


def _clean(s):
    """Collapse whitespace; strip control chars. Canvas-rendered text is safe
    from injection, so we don't HTML-escape here."""
    if not isinstance(s, str):
        s = '' if s is None else str(s)
    return s.replace('\r', ' ').replace('\n', ' ').strip()


def _darken(hex_color, factor=0.65):
    try:
        h = hex_color.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return '#%02x%02x%02x' % (int(r * factor), int(g * factor), int(b * factor))
    except Exception:
        return '#333333'


# ── Language / script detection ────────────────────────────────────

def _script_of_char(ch):
    """Map a character to a coarse script family, or None for punctuation/
    digits/whitespace that carry no language signal."""
    if not ch.strip() or ch.isdigit():
        return None
    cp = ord(ch)
    if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF:
        return 'Han'
    if 0x3040 <= cp <= 0x30FF:
        return 'Kana'
    if 0xAC00 <= cp <= 0xD7A3 or 0x1100 <= cp <= 0x11FF:
        return 'Hangul'
    if 0x0400 <= cp <= 0x04FF:
        return 'Cyrillic'
    if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
        return 'Arabic'
    try:
        if 'LATIN' in unicodedata.name(ch):
            return 'Latin'
    except ValueError:
        return None
    return None


def dominant_script(strings):
    counts = {}
    for s in strings:
        for ch in s or '':
            fam = _script_of_char(ch)
            if fam:
                counts[fam] = counts.get(fam, 0) + 1
    if not counts:
        return 'Latin'
    return max(counts, key=counts.get)


def resolve_lang(graph, requested):
    if requested in ('zh', 'en'):
        return requested
    sample = []
    for e in graph.get('entities', []):
        sample.append(e.get('name', ''))
        sample.append(e.get('description', ''))
    for et in graph.get('schema', {}).get('entity_types', []):
        sample.append(et.get('type', ''))
    fam = dominant_script(sample)
    # UI ships only en/zh; CJK-family graphs get the zh UI, everything else en.
    return 'zh' if fam in ('Han', 'Kana', 'Hangul') else 'en'


# ── Type styling (language-agnostic) ───────────────────────────────

def assign_styles(entities):
    counts = {}
    for e in entities:
        counts[e['type']] = counts.get(e['type'], 0) + 1
    ordered = sorted(counts, key=lambda t: (-counts[t], t))
    colors, shapes, borders = {}, {}, {}
    for i, t in enumerate(ordered):
        c = KNOWN_COLORS.get(t) or PALETTE[i % len(PALETTE)]
        colors[t] = c
        borders[t] = _darken(c)
        shapes[t] = KNOWN_SHAPES.get(t) or SHAPE_CYCLE[i % len(SHAPE_CYCLE)]
    return counts, ordered, colors, shapes, borders


# ── Layout precomputation ──────────────────────────────────────────

def _degree_counts(entities, relationships):
    degrees = {e['id']: 0 for e in entities}
    for r in relationships:
        if r.get('source') in degrees:
            degrees[r['source']] += 1
        if r.get('target') in degrees:
            degrees[r['target']] += 1
    return degrees


def _node_size(degree):
    """Keep the viewer's historical connection-count size rule."""
    return min(10 + degree * 1.2, 42)


def _ring_radius(ids, collision_radii, floor=0):
    """Return a circle radius whose adjacent node boundaries cannot touch."""
    n = len(ids)
    if n <= 1:
        return floor
    widest = max(collision_radii[eid] for eid in ids)
    min_chord = 2 * widest
    return max(floor, min_chord / (2 * math.sin(math.pi / n)))


def _on_ring(ids, radius, start=-math.pi / 2):
    n = len(ids)
    if not n:
        return {}
    if n == 1 and radius == 0:
        return {ids[0]: [0, 0]}
    return {
        eid: [radius * math.cos(start + 2 * math.pi * i / n),
              radius * math.sin(start + 2 * math.pi * i / n)]
        for i, eid in enumerate(ids)
    }


def _grid_positions(ids, collision_radii):
    """Pack nodes into a centered grid with size-aware rows and columns."""
    if not ids:
        return {}
    cols = max(1, math.ceil(math.sqrt(len(ids) * 1.35)))
    rows = math.ceil(len(ids) / cols)
    col_r = [0] * cols
    row_r = [0] * rows
    for i, eid in enumerate(ids):
        row, col = divmod(i, cols)
        col_r[col] = max(col_r[col], collision_radii[eid])
        row_r[row] = max(row_r[row], collision_radii[eid])

    xs = [0]
    for col in range(1, cols):
        xs.append(xs[-1] + col_r[col - 1] + col_r[col])
    ys = [0]
    for row in range(1, rows):
        ys.append(ys[-1] + row_r[row - 1] + row_r[row])
    x_mid = ((xs[0] - col_r[0]) + (xs[-1] + col_r[-1])) / 2
    y_mid = ((ys[0] - row_r[0]) + (ys[-1] + row_r[-1])) / 2
    return {
        eid: [xs[i % cols] - x_mid, ys[i // cols] - y_mid]
        for i, eid in enumerate(ids)
    }


def _line_positions(ids, collision_radii):
    """Place one hierarchy level on a centered, collision-free line."""
    if not ids:
        return {}
    xs = [0]
    for i in range(1, len(ids)):
        xs.append(xs[-1] + collision_radii[ids[i - 1]] +
                  collision_radii[ids[i]])
    left = xs[0] - collision_radii[ids[0]]
    right = xs[-1] + collision_radii[ids[-1]]
    mid = (left + right) / 2
    return {eid: xs[i] - mid for i, eid in enumerate(ids)}


def _hierarchical_positions(entities, relationships, collision_radii,
                            degrees):
    """Build a deterministic layered layout, including cyclic components."""
    ids = [e['id'] for e in entities]
    order = {eid: i for i, eid in enumerate(ids)}
    adjacency = {eid: set() for eid in ids}
    indegree = {eid: 0 for eid in ids}
    for r in relationships:
        source, target = r.get('source'), r.get('target')
        if source not in adjacency or target not in adjacency:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
        if source != target:
            indegree[target] += 1

    components, unseen = [], set(ids)
    while unseen:
        seed = min(unseen, key=lambda eid: order[eid])
        stack, component = [seed], []
        unseen.remove(seed)
        while stack:
            eid = stack.pop()
            component.append(eid)
            for other in sorted(adjacency[eid], key=lambda x: order[x],
                                reverse=True):
                if other in unseen:
                    unseen.remove(other)
                    stack.append(other)
        components.append(sorted(component, key=lambda eid: order[eid]))

    layouts = []
    for component in components:
        roots = [eid for eid in component if indegree[eid] == 0]
        if not roots:
            roots = [max(component, key=lambda eid: (degrees[eid],
                                                     -order[eid]))]
        roots.sort(key=lambda eid: (-degrees[eid], order[eid]))
        level = {eid: 0 for eid in roots}
        queue = list(roots)
        qi = 0
        while qi < len(queue):
            eid = queue[qi]
            qi += 1
            for other in sorted(adjacency[eid], key=lambda x: order[x]):
                if other not in level:
                    level[other] = level[eid] + 1
                    queue.append(other)
        for eid in component:
            level.setdefault(eid, 0)

        buckets = {}
        for eid in component:
            buckets.setdefault(level[eid], []).append(eid)
        local = {}
        previous_y = previous_r = 0
        first = True
        for li in sorted(buckets):
            row = buckets[li]
            row.sort(key=lambda eid: (-degrees[eid], order[eid]))
            row_r = max(collision_radii[eid] for eid in row)
            y = 0 if first else previous_y + previous_r + row_r + LEVEL_GAP
            first = False
            for eid, x in _line_positions(row, collision_radii).items():
                local[eid] = [x, y]
            previous_y, previous_r = y, row_r

        min_x = min(local[eid][0] - collision_radii[eid]
                    for eid in component)
        max_x = max(local[eid][0] + collision_radii[eid]
                    for eid in component)
        layouts.append((local, component, min_x, max_x))

    result, cursor = {}, 0
    for local, component, min_x, max_x in layouts:
        shift = cursor - min_x
        for eid in component:
            result[eid] = [local[eid][0] + shift, local[eid][1]]
        cursor += max_x - min_x + COMPONENT_GAP
    if result:
        min_x = min(result[eid][0] - collision_radii[eid] for eid in result)
        max_x = max(result[eid][0] + collision_radii[eid] for eid in result)
        mid = (min_x + max_x) / 2
        for point in result.values():
            point[0] -= mid
    return result


def _edge_routes(relationships):
    """Assign a distinct curve lane to every relationship edge."""
    grouped = {}
    for i, r in enumerate(relationships):
        source, target = r['source'], r['target']
        key = (source, target) if str(source) <= str(target) else (target, source)
        grouped.setdefault(key, []).append(i)

    routes = [None] * len(relationships)
    for group_index, (key, edge_indexes) in enumerate(grouped.items()):
        if key[0] == key[1]:
            for lane, edge_index in enumerate(edge_indexes):
                routes[edge_index] = {
                    'smooth': {'enabled': False},
                    'selfReference': {
                        'size': 28 + lane * 14,
                        'angle': (math.pi / 4 + lane * math.pi / 5) %
                                 (2 * math.pi),
                        'renderBehindTheNode': False,
                    },
                }
            continue

        for lane_index, edge_index in enumerate(edge_indexes):
            if len(edge_indexes) == 1:
                physical_lane = 1 if group_index % 2 else -1
                roundness = 0.08 + 0.02 * (group_index % 3)
            else:
                magnitude = lane_index // 2 + 1
                physical_lane = -magnitude if lane_index % 2 == 0 else magnitude
                side_count = (len(edge_indexes) + 1) // 2
                # Normalize into a useful curve range without capping: even
                # very large parallel-edge groups keep a unique roundness.
                roundness = 0.08 + 0.52 * magnitude / (side_count + 2)
            r = relationships[edge_index]
            oriented_lane = physical_lane if r['source'] == key[0] else -physical_lane
            routes[edge_index] = {
                'smooth': {
                    'enabled': True,
                    'type': 'curvedCW' if oriented_lane > 0 else 'curvedCCW',
                    'roundness': roundness,
                }
            }
    return routes


def build_layouts(entities, relationships, ordered_types, node_sizes=None):
    by_type = {}
    for e in entities:
        by_type.setdefault(e['type'], []).append(e['id'])
    ids = [e['id'] for e in entities]
    order = {eid: i for i, eid in enumerate(ids)}
    degrees = _degree_counts(entities, relationships)
    if node_sizes is None:
        node_sizes = {eid: _node_size(degrees[eid]) for eid in ids}
    # Treat half the desired gap as part of each collision radius. Pairwise
    # separation can then be checked with radius_a + radius_b everywhere.
    collision_radii = {eid: node_sizes[eid] + NODE_GAP / 2 for eid in ids}

    circular = _on_ring(ids,
                        _ring_radius(ids, collision_radii, floor=260))

    type_ids = [eid for t in ordered_types for eid in by_type.get(t, [])]
    tc = _on_ring(type_ids,
                  _ring_radius(type_ids, collision_radii, floor=260))

    hubs = {}
    if ids:
        hub_id = max(ids, key=lambda eid: (degrees[eid], -order[eid]))
        hubs[hub_id] = [0, 0]
        others = [eid for eid in ids if eid != hub_id]
        if others:
            outer_r = _ring_radius(others, collision_radii, floor=220)
            outer_r = max(
                outer_r,
                collision_radii[hub_id] +
                max(collision_radii[eid] for eid in others) + 120)
            hubs.update(_on_ring(others, outer_r))

    # Concentric rings expand for both within-ring and cross-ring clearance.
    conc = {}
    previous_r = previous_max = 0
    first_ring = True
    for t in ordered_types:
        ring_ids = by_type[t]
        current_max = max(collision_radii[eid] for eid in ring_ids)
        floor = 0 if first_ring and len(ring_ids) == 1 else 120
        rr = _ring_radius(ring_ids, collision_radii, floor=floor)
        if not first_ring:
            rr = max(rr, previous_r + previous_max + current_max)
        conc.update(_on_ring(ring_ids, rr, start=0))
        previous_r, previous_max, first_ring = rr, current_max, False

    grid = _grid_positions(type_ids, collision_radii)
    hierarchical = _hierarchical_positions(
        entities, relationships, collision_radii, degrees)

    isolated = [eid for eid in ids if degrees[eid] == 0]
    connected = [eid for eid in ids if degrees[eid] > 0]
    force = _grid_positions(connected, collision_radii)
    connected_outer = max(
        (math.hypot(*force[eid]) + collision_radii[eid]
         for eid in connected), default=0)
    isolate_min_r = _ring_radius(isolated, collision_radii, floor=180)
    if isolated and connected:
        isolate_min_r = max(
            isolate_min_r,
            connected_outer + max(collision_radii[eid] for eid in isolated) +
            2 * NODE_GAP)
    force.update(_on_ring(isolated, isolate_min_r))

    return {'posCircular': circular, 'posTypeCirc': tc, 'posHub': hubs,
            'posConc': conc, 'posGrid': grid, 'posHier': hierarchical,
            'posForce': force, 'isolatedIds': isolated,
            'forceIsolateMinRadius': isolate_min_r,
            'layoutGap': NODE_GAP,
            'collisionRadii': collision_radii}


# ── Data build ─────────────────────────────────────────────────────

def build_data(graph, lang):
    entities = graph['entities']
    relationships = graph['relationships']
    counts, ordered, colors, shapes, borders = assign_styles(entities)

    degrees = _degree_counts(entities, relationships)
    node_sizes = {e['id']: _node_size(degrees[e['id']]) for e in entities}

    nodes = []
    for e in entities:
        deg = degrees.get(e['id'], 0)
        size = node_sizes[e['id']]
        t = e['type']
        desc = _clean(e.get('description', ''))
        nodes.append(dict(
            id=e['id'], label=_clean(e['name']),
            title=_esc_html((desc[:150] + '…') if len(desc) > 150 else desc),
            color=colors.get(t, '#AAAAAA'), shape=shapes.get(t, 'dot'),
            size=size, font={'size': max(11, min(15, int(size / 2.0)))},
            group=t, etype=t, deg=deg, isolated=(deg == 0),
            desc=desc, aliases=e.get('aliases', [])[:6],
            conf=e.get('confidence'), chunks=e.get('source_chunks', [])[:8],
        ))

    edges = []
    routes = _edge_routes(relationships)
    for edge_index, r in enumerate(relationships):
        ev = _clean(r.get('evidence', '') or r.get('description', ''))
        edges.append({
            'from': r['source'], 'to': r['target'], 'label': _clean(r['type']),
            'title': _esc_html(ev[:160]),
            'etype': _clean(r['type']),
            'desc': _clean(r.get('description', '')),
            'evidence': _clean(r.get('evidence', '')),
            'conf': r.get('confidence'),
            'chunks': r.get('source_chunks', [])[:8],
            **routes[edge_index],
        })

    data = dict(nodes=nodes, edges=edges, typeColors=colors,
                typeBorders=borders, typeShapes=shapes, typeCounts=counts,
                orderedTypes=ordered, lang=lang)
    data.update(build_layouts(entities, relationships, ordered, node_sizes))
    return data


# ── CSS (CJK-aware font stack) ─────────────────────────────────────

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#16162c;--panel:rgba(22,22,44,0.97);--line:#33334d;--txt:#dcdcf0;--muted:#9090b0;--accent:#6f8fd6}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;background:#1a1a2e;overflow:hidden;height:100vh;color:var(--txt)}
#app{display:flex;height:100vh}
#sb{width:310px;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column;z-index:10;transition:width 0.25s}
#sb.collapsed{width:36px}
#sbt{position:absolute;left:310px;top:12px;z-index:20;background:rgba(22,22,44,0.9);border:1px solid #444;color:#aaa;width:28px;height:36px;border-radius:0 8px 8px 0;cursor:pointer;font-size:14px;line-height:34px;text-align:center;transition:left 0.25s}
#sb.collapsed+#sbt{left:36px}
#sb.collapsed .sc{display:none}
#sb.collapsed #dp{display:none}
.sc{padding:14px;overflow-y:auto;flex:1;min-height:0}
h2{color:#eaeaff;font-size:15px;margin-bottom:12px;border-bottom:1px solid var(--line);padding-bottom:8px;display:flex;align-items:center;gap:6px}
select,input{width:100%;padding:8px 10px;background:#242440;border:1px solid #444;border-radius:8px;color:var(--txt);font-size:13px;margin-bottom:8px;outline:none}
select:focus,input:focus{border-color:var(--accent)}
option{background:#242440}
.ft{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin:12px 0 6px}
#sr{max-height:150px;overflow-y:auto;margin-bottom:6px}
.si{padding:5px 8px;cursor:pointer;color:#b6b6d6;font-size:12px;border-radius:5px}
.si:hover{background:#2c2c4a;color:#fff}
.fr{display:flex;align-items:center;padding:3px 4px;font-size:12px;color:#b6b6d6;border-radius:5px;cursor:pointer}
.fr:hover{background:#242440}
.fr input{margin-right:6px;width:auto;accent-color:var(--accent)}
.fd{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex:none}
.fc{margin-left:auto;font-size:10px;opacity:.55}
.btn{background:#242440;border:1px solid #444;color:#c6c6e6;padding:8px 12px;border-radius:8px;cursor:pointer;font-size:12px;width:100%;margin-bottom:6px;transition:.15s}
.btn:hover{background:#2f2f52;color:#fff;border-color:#555}
.br{display:flex;gap:6px}
.br .btn{flex:1;margin-bottom:0}
#dp{background:#1e1e3c;border-top:1px solid var(--line);display:flex;flex-direction:column;flex:none;max-height:46vh;font-size:12px}
.dph{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid #262640;flex:none}
.dpt{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.dpbtn{background:transparent;border:1px solid #3a3a5a;color:#9a9ac0;border-radius:6px;font-size:11px;padding:2px 9px;cursor:pointer;margin-left:6px}
.dpbtn:hover{color:#fff;border-color:#666}
#dpc{padding:10px 12px;overflow-y:auto;min-height:64px}
.solo{margin-left:8px;font-size:10px;color:#7f8fc9;cursor:pointer;opacity:0;transition:.15s;flex:none}
.fr:hover .solo{opacity:1}
.solo:hover{color:#fff;text-decoration:underline}
#dp h3{color:#fff;font-size:15px;margin-bottom:5px;word-break:break-word}
#dp .meta{color:var(--muted);font-size:11px;margin-bottom:4px}
#dp .chip{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;margin-right:4px}
#dp .desc{color:#c2c2de;line-height:1.5;margin:6px 0}
#dp .ev{color:#8fce8f;font-size:11px;font-style:italic;margin-top:6px;padding:6px 8px;background:rgba(80,200,80,.06);border-left:2px solid rgba(80,200,80,.4);border-radius:0 5px 5px 0}
.nbrs{margin-top:6px}
.nb{display:flex;align-items:center;gap:6px;padding:4px 6px;border-radius:5px;cursor:pointer;color:#b6b6d6}
.nb:hover{background:#2c2c4a;color:#fff}
.nb .arw{color:var(--accent);font-weight:700;flex:none}
.nb .rel{color:var(--muted);font-size:10px}
.de{color:#555;text-align:center;padding:22px 0}
#nc{flex:1;position:relative}
#net{width:100%;height:100%}
#st{position:absolute;bottom:8px;left:50%;transform:translateX(-50%);background:rgba(22,22,44,.92);border:1px solid var(--line);border-radius:10px;padding:6px 16px;font-size:11px;color:var(--muted);z-index:5}
#st b{color:#eaeaff}
#hint{position:absolute;bottom:42px;right:16px;font-size:10px;color:#5a5a7a;z-index:5}
#load{position:absolute;inset:0;background:rgba(20,20,38,.85);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:30;gap:14px;color:var(--muted);font-size:13px}
#load.hidden{display:none}
.spin{width:38px;height:38px;border:3px solid #33334d;border-top-color:var(--accent);border-radius:50%;animation:sp 0.9s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
#help{position:absolute;inset:0;background:rgba(12,12,24,.72);display:none;align-items:center;justify-content:center;z-index:40}
#help.show{display:flex}
.hcard{background:#1e1e3c;border:1px solid var(--line);border-radius:14px;padding:22px 26px;max-width:420px;width:90%}
.hcard h3{color:#fff;font-size:16px;margin-bottom:12px}
.hrow{display:flex;justify-content:space-between;padding:5px 0;font-size:12px;color:#c2c2de;border-bottom:1px solid #262640}
.hrow kbd{background:#2c2c4a;border:1px solid #444;border-radius:5px;padding:1px 7px;font-size:11px;color:#eaeaff}
.hclose{margin-top:14px}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#3a3a5a;border-radius:3px}
"""

# ── JavaScript (vis-network 9.x compatible, readable form) ─────────

JS_CODE = r"""
function esc(s){return (s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var T = D.i18n;
var NM={}; D.nodes.forEach(function(n){NM[n.id]=n;});
var NE={}; D.edges.forEach(function(e,i){ e.id='e'+i; (NE[e.from]=NE[e.from]||[]).push(e); (NE[e.to]=NE[e.to]||[]).push(e); });
var labById={}; D.edges.forEach(function(e){labById[e.id]=e.label;});

// Dense graphs start with edge labels hidden to reduce clutter; labels for the
// selected node's neighbourhood are still revealed on click (see HN).
var DENSE = D.edges.length>60;
var edgeLabels = !DENSE;
function EFONT(){ return {size:10,color:'#9a9ac0',strokeWidth:3,strokeColor:'#1a1a2e'}; }
function DIMFONT(){ return {size:10,color:'rgba(0,0,0,0)',strokeWidth:0,strokeColor:'#1a1a2e'}; }
function HIFONT(){ return {size:11,color:'#cfd8ff',strokeWidth:3,strokeColor:'#1a1a2e'}; }

var VN=D.nodes.map(function(n){
  var p=D.posForce[n.id]||[0,0];
  return {id:n.id,label:n.label,title:n.title,color:n.color,shape:n.shape,
    size:n.size,font:n.font,group:n.group,x:p[0],y:p[1],
    mass:1+Math.min(n.deg,20)*0.08,
    fixed:n.isolated?{x:true,y:true}:false};
});
var VE=D.edges.map(function(e){return {id:e.id,from:e.from,to:e.to,
  label:edgeLabels?e.label:'',title:e.title,color:{color:'#5a5a7a',opacity:0.35},
  arrows:'to',font:EFONT(),smooth:e.smooth,selfReference:e.selfReference};});
var AN=new vis.DataSet(VN), AE=new vis.DataSet(VE);

var PN={barnesHut:{gravitationalConstant:-4200,centralGravity:0.18,
  springLength:190,springConstant:0.025,damping:0.38,avoidOverlap:1},
  minVelocity:0.2,stabilization:{enabled:true,iterations:900,
  updateInterval:25,fit:false}};
var GRP={}; Object.keys(D.typeColors).forEach(function(k){GRP[k]={color:{background:D.typeColors[k],border:D.typeBorders[k]||D.typeColors[k]}};});

var network=new vis.Network(document.getElementById('net'),{nodes:AN,edges:AE},{
  physics:PN,
  nodes:{borderWidth:2},
  edges:{arrows:{to:{enabled:true,scaleFactor:0.4}},smooth:false,
    selectionWidth:2,hoverWidth:1.5},
  interaction:{hover:true,tooltipDelay:90,navigationButtons:true,keyboard:false},
  layout:{hierarchical:false}, groups:GRP
});

var lk=false, cv='force', sn=null, hist=[], isoOf=null;
var typeOn={}; D.orderedTypes.forEach(function(t){typeOn[t]=true;});
function US(){ var vis_n=AN.get({filter:function(n){return !n.hidden;}}).length; var vis_e=AE.get({filter:function(e){return !e.hidden;}}).length; document.getElementById('st').innerHTML=T.nodes+' <b>'+vis_n+'</b> / '+AN.length+'  ·  '+T.edges+' <b>'+vis_e+'</b> / '+AE.length; }
US();

// ── Type filter (doubles as legend: colour + type + count) ──
var fc=document.getElementById('tf');
D.orderedTypes.forEach(function(t){
  var c=D.typeColors[t]||'#aaa';
  var r=document.createElement('label'); r.className='fr';
  var cb=document.createElement('input'); cb.type='checkbox'; cb.checked=true;
  cb.addEventListener('change',function(){typeOn[t]=cb.checked; isoOf=null; applyFilters();});
  var dot=document.createElement('span'); dot.className='fd'; dot.style.background=c;
  var name=document.createElement('span'); name.textContent=t;
  var cnt=document.createElement('span'); cnt.className='fc'; cnt.textContent=D.typeCounts[t];
  var solo=document.createElement('span'); solo.className='solo'; solo.textContent=T.only;
  solo.addEventListener('click',function(ev){ ev.preventDefault(); ev.stopPropagation();
    D.orderedTypes.forEach(function(x){typeOn[x]=(x===t);});
    var boxes=document.querySelectorAll('#tf input');
    D.orderedTypes.forEach(function(x,i){boxes[i].checked=typeOn[x];});
    isoOf=null; applyFilters();
  });
  r.appendChild(cb); r.appendChild(dot); r.appendChild(name); r.appendChild(cnt); r.appendChild(solo);
  fc.appendChild(r);
});
function NB(nid){ var m={}; (NE[nid]||[]).forEach(function(e){m[e.from]=1;m[e.to]=1;}); return m; }
function applyFilters(){
  var nb=isoOf?NB(isoOf):null;
  var un=[]; AN.forEach(function(n){ var vis=typeOn[n.group]!==false; if(nb) vis=vis&&(n.id===isoOf||nb[n.id]); un.push({id:n.id,hidden:!vis}); }); AN.update(un);
  var ue=[]; AE.forEach(function(e){var a=AN.get(e.from),b=AN.get(e.to); ue.push({id:e.id,hidden:(a&&a.hidden)||(b&&b.hidden)});}); AE.update(ue);
  US();
}

// ── Search ──
var sbox=document.getElementById('sbox'), sr=document.getElementById('sr');
sbox.addEventListener('input',function(){
  var q=sbox.value.trim().toLowerCase(); sr.innerHTML=''; if(!q)return;
  D.nodes.filter(function(n){return n.label.toLowerCase().indexOf(q)>=0;}).slice(0,12).forEach(function(n){
    var d=document.createElement('div'); d.className='si'; d.textContent=n.label+'  ['+n.etype+']';
    d.addEventListener('click',function(){FN(n.id);renderNode(n.id);});
    sr.appendChild(d);
  });
});
sbox.addEventListener('keydown',function(e){ if(e.key==='Enter'&&sr.firstChild){ sr.firstChild.click(); sbox.blur(); } });

// ── Layout switching ──
function AL(pm){
  network.setOptions({physics:false,layout:{hierarchical:false}});
  var ups=[];
  AN.forEach(function(n){var p=pm?pm[n.id]:null;
    if(p)ups.push({id:n.id,x:p[0],y:p[1],fixed:false});
  });
  if(ups.length)AN.update(ups);
  network.fit({animation:false});
}
function GP(v){ return {circular:D.posCircular,'type-circular':D.posTypeCirc,
  'hub-spoke':D.posHub,concentric:D.posConc,grid:D.posGrid,
  hierarchical:D.posHier}[v]||null; }
function PFI(){
  var ups=[];
  D.nodes.forEach(function(n){var p=D.posForce[n.id]||[0,0];
    ups.push({id:n.id,x:p[0],y:p[1],
      fixed:n.isolated?{x:true,y:true}:false});
  });
  AN.update(ups);
}
function RNC(){
  if(cv!=='force')return;
  var active=D.nodes.filter(function(n){return !n.isolated;}),pos=network.getPositions();
  for(var pass=0;pass<10;pass++){
    var moved=false;
    for(var i=0;i<active.length;i++)for(var j=i+1;j<active.length;j++){
      var a=active[i],b=active[j],pa=pos[a.id],pb=pos[b.id];
      if(!pa||!pb)continue;
      var dx=pb.x-pa.x,dy=pb.y-pa.y,dist=Math.hypot(dx,dy);
      var need=(D.collisionRadii[a.id]||a.size)+(D.collisionRadii[b.id]||b.size);
      if(dist+0.1>=need)continue;
      if(dist<0.001){var ang=((i+1)*37+(j+1)*17)%360*Math.PI/180;
        dx=Math.cos(ang);dy=Math.sin(ang);dist=1;
      }
      var push=(need-dist)/2+0.5,ux=dx/dist,uy=dy/dist;
      pa.x-=ux*push;pa.y-=uy*push;pb.x+=ux*push;pb.y+=uy*push;moved=true;
    }
    if(!moved)break;
  }
  var ups=[];active.forEach(function(n){var p=pos[n.id];if(p)ups.push({id:n.id,x:p.x,y:p.y});});
  if(ups.length)AN.update(ups);
}
function POI(){
  if(cv!=='force'||!D.isolatedIds.length)return;
  var pos=network.getPositions(), connected=D.nodes.filter(function(n){return !n.isolated;});
  var cx=0,cy=0,body=0;
  if(connected.length){
    var minx=Infinity,maxx=-Infinity,miny=Infinity,maxy=-Infinity;
    connected.forEach(function(n){var p=pos[n.id]||{x:0,y:0},r=D.collisionRadii[n.id]||n.size;
      minx=Math.min(minx,p.x-r);maxx=Math.max(maxx,p.x+r);
      miny=Math.min(miny,p.y-r);maxy=Math.max(maxy,p.y+r);
    });
    cx=(minx+maxx)/2;cy=(miny+maxy)/2;
    connected.forEach(function(n){var p=pos[n.id]||{x:0,y:0},r=D.collisionRadii[n.id]||n.size;
      body=Math.max(body,Math.hypot(p.x-cx,p.y-cy)+r);
    });
  }
  var maxIso=0;
  D.isolatedIds.forEach(function(id){maxIso=Math.max(maxIso,D.collisionRadii[id]||10);});
  var rr=Math.max(D.forceIsolateMinRadius,body+maxIso+2*D.layoutGap);
  var ups=[],count=D.isolatedIds.length;
  D.isolatedIds.forEach(function(id,i){var a=-Math.PI/2+2*Math.PI*i/count;
    ups.push({id:id,x:cx+rr*Math.cos(a),y:cy+rr*Math.sin(a),
      fixed:{x:true,y:true}});
  });
  AN.update(ups);
}
function SV(v){
  cv=v;
  if(v==='force'){
    PFI();
    network.setOptions({layout:{hierarchical:false},physics:lk?false:PN});
    if(!lk)network.stabilize(900);
    network.fit({animation:true});
  } else { AL(GP(v)); }
  document.getElementById('vs').value=v;
}
document.getElementById('vs').addEventListener('change',function(){SV(this.value);});

// ── Sidebar / lock / edge-labels / png ──
function TS(){ var s=document.getElementById('sb'); s.classList.toggle('collapsed'); document.getElementById('sbt').innerHTML=s.classList.contains('collapsed')?'▶':'◀'; setTimeout(function(){network.fit();},300); }
function TL(){ lk=!lk; var b=document.getElementById('bl'); if(lk){network.setOptions({physics:false}); b.textContent=T.locked; b.style.borderColor='#C44E52';} else {network.setOptions({physics:cv==='force'?PN:false}); b.textContent=T.drag; b.style.borderColor='#444';} }
function TE(){ edgeLabels=!edgeLabels; if(sn){ HN(sn); } else { var ups=[]; AE.forEach(function(e){ups.push({id:e.id,label:edgeLabels?labById[e.id]:''});}); AE.update(ups); } var b=document.getElementById('be'); b.textContent=edgeLabels?T.edgeOn:T.edgeOff; }
function PNGX(){ var c=document.querySelector('#net canvas'); if(!c)return; var a=document.createElement('a'); a.href=c.toDataURL('image/png'); a.download='knowledge_graph.png'; a.click(); }

// ── Detail panel ──
function chip(txt,bg){ return '<span class="chip" style="background:'+bg+'">'+esc(txt)+'</span>'; }
function renderNode(nid,push){
  var n=NM[nid]; if(!n)return;
  var sb2=document.getElementById('sb'); if(sb2.classList.contains('collapsed'))TS();
  if(push!==false && sn && sn!==nid) hist.push(sn);
  sn=nid;
  document.getElementById('bk').style.display=hist.length?'':'none';
  var d=document.getElementById('dpc');
  var html='<h3>'+esc(n.label)+'</h3>';
  html+='<div class="meta">'+chip(n.etype,(D.typeColors[n.etype]||'#555'))+' '+n.deg+' '+T.edgesLc+(n.conf!=null?'  ·  '+T.conf+' '+n.conf:'')+'</div>';
  if(n.desc) html+='<div class="desc">'+esc(n.desc)+'</div>';
  if(n.aliases&&n.aliases.length) html+='<div class="meta">'+T.aliases+': '+esc(n.aliases.join(', '))+'</div>';
  if(n.chunks&&n.chunks.length) html+='<div class="meta">'+T.source+': '+esc(n.chunks.join(', '))+'</div>';
  html+='<button class="btn" id="isoBtn" style="margin-top:8px">'+(isoOf===nid?T.showAll:T.isolate)+'</button>';
  var nbrs=NE[nid]||[];
  html+='<div class="ft">'+T.connections+' ('+nbrs.length+')</div><div class="nbrs" id="nbrs"></div>';
  d.innerHTML=html;
  document.getElementById('isoBtn').addEventListener('click',function(){ISO(nid);});
  var box=document.getElementById('nbrs');
  if(!nbrs.length){ box.innerHTML='<div class="de" style="padding:8px">'+T.noconn+'</div>'; }
  nbrs.slice(0,60).forEach(function(e){
    var out=e.from===nid, oid=out?e.to:e.from, o=NM[oid]; if(!o)return;
    var row=document.createElement('div'); row.className='nb';
    var arw=document.createElement('span'); arw.className='arw'; arw.textContent=out?'→':'←';
    var nm=document.createElement('span'); nm.textContent=o.label;
    var rel=document.createElement('span'); rel.className='rel'; rel.textContent=e.label;
    row.appendChild(arw); row.appendChild(nm); row.appendChild(rel);
    row.addEventListener('click',function(){FN(oid);renderNode(oid);});
    box.appendChild(row);
  });
  HN(nid);
}
function renderEdge(eid){
  var e=AE.get(eid), fr=NM[e.from], to=NM[e.to]; if(!fr||!to)return;
  var sb2=document.getElementById('sb'); if(sb2.classList.contains('collapsed'))TS();
  var full=D.edges.filter(function(x){return x.id===eid;})[0]||{};
  var d=document.getElementById('dpc');
  var h='<h3>'+esc(fr.label)+' <span style="color:#6f8fd6">→</span> '+esc(to.label)+'</h3>';
  h+='<div class="meta">'+chip(e.label,'#3a3a5a')+(full.conf!=null?'  ·  '+T.conf+' '+full.conf:'')+'</div>';
  if(full.desc) h+='<div class="desc">'+esc(full.desc)+'</div>';
  if(full.evidence) h+='<div class="ev">“'+esc(full.evidence)+'”</div>';
  if(full.chunks&&full.chunks.length) h+='<div class="meta" style="margin-top:5px">'+T.source+': '+esc(full.chunks.join(', '))+'</div>';
  d.innerHTML=h;
}
network.on('click',function(p){ if(p.nodes.length){renderNode(p.nodes[0]);} else if(p.edges.length){renderEdge(p.edges[0]);} else CS(); });
network.on('doubleClick',function(p){ if(p.nodes.length)FN(p.nodes[0]); else FG(); });

function HN(nid){
  var nb=NB(nid);
  var un=[]; AN.forEach(function(n){var on=nb[n.id]||n.id===nid; un.push({id:n.id,opacity:on?1:0.12,font:{size:on?13:8,color:on?'#eee':'#3a3a55'}});}); AN.update(un);
  var ue=[]; AE.forEach(function(e){var h=e.from===nid||e.to===nid;
    ue.push({id:e.id,
      color:{color:h?'#8fa6e0':'#2a2a3a',opacity:h?0.9:0.05},
      width:h?2.2:0.5,
      label:h?labById[e.id]:(edgeLabels?labById[e.id]:''),
      font:h?HIFONT():DIMFONT()});
  }); AE.update(ue);
}
function ISO(nid){ isoOf=(isoOf===nid?null:nid); applyFilters(); if(isoOf) network.fit({animation:true}); renderNode(nid,false); }
function BACK(){ if(!hist.length)return; var id=hist.pop(); FN(id); renderNode(id,false); }
function CS(){ sn=null; hist=[]; if(isoOf){isoOf=null; applyFilters();}
  document.getElementById('bk').style.display='none';
  document.getElementById('dpc').innerHTML='<div class="de">'+T.clickhint+'</div>';
  var un=[]; AN.forEach(function(n){un.push({id:n.id,opacity:1,font:{size:12,color:'#dcdcf0'}});}); AN.update(un);
  var ue=[]; AE.forEach(function(e){ue.push({id:e.id,color:{color:'#5a5a7a',opacity:0.35},width:1,label:edgeLabels?labById[e.id]:'',font:EFONT()});}); AE.update(ue); }
function FN(nid){ network.selectNodes([nid]); network.focus(nid,{scale:1.4,animation:true}); }
function FG(){ network.fit({animation:true}); }
function RV(){ isoOf=null; hist=[]; edgeLabels=!DENSE; CS(); D.orderedTypes.forEach(function(t){typeOn[t]=true;}); document.querySelectorAll('#tf input').forEach(function(c){c.checked=true;}); applyFilters(); lk=false; var b=document.getElementById('bl'); b.textContent=T.drag; b.style.borderColor='#444'; document.getElementById('be').textContent=edgeLabels?T.edgeOn:T.edgeOff; SV('force'); US(); }
function HELP(){ document.getElementById('help').classList.toggle('show'); }

document.addEventListener('keydown',function(e){
  var typing=document.activeElement===sbox;
  if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();sbox.focus();return;}
  if(e.key==='Escape'){ if(document.getElementById('help').classList.contains('show'))HELP(); else CS(); return; }
  if(typing)return;
  if(e.key==='l'||e.key==='L')TL();
  if(e.key==='f'||e.key==='F')FG();
  if(e.key==='b'||e.key==='B')BACK();
  if(e.key==='?'||e.key==='h'||e.key==='H')HELP();
  if(e.key==='v'||e.key==='V'){ var s=document.getElementById('vs'),v=['force','circular','type-circular','hub-spoke','concentric','grid','hierarchical']; s.value=v[(v.indexOf(s.value)+1)%v.length]; SV(s.value); }
});

document.getElementById('be').textContent=edgeLabels?T.edgeOn:T.edgeOff;
document.getElementById('bk').addEventListener('click',BACK);
document.getElementById('dpx').addEventListener('click',function(){ try{network.unselectAll();}catch(err){} CS(); });

network.on('stabilizationIterationsDone',function(){
  network.stopSimulation(); RNC(); POI(); network.stopSimulation();
  document.getElementById('load').classList.add('hidden');
  network.fit({animation:true});
});
setTimeout(function(){ network.stopSimulation(); RNC(); POI(); network.stopSimulation(); document.getElementById('load').classList.add('hidden'); }, 5000);
"""

HTML_TEMPLATE = """\
<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
<style>{css}</style></head><body>
<div id="app">
  <div id="sb"><div class="sc">
    <h2>{title}</h2>
    <div class="ft">{view_label}</div>
    <select id="vs">{view_options}</select>
    <div class="ft">{search_label}</div>
    <input type="text" id="sbox" placeholder="{search_placeholder}" autocomplete="off"><div id="sr"></div>
    <div class="ft">{filter_label}</div><div id="tf"></div>
    <div class="ft">{controls_label}</div>
    <div class="br"><button class="btn" onclick="FG()">{fit_btn}</button><button class="btn" id="bl" onclick="TL()">{drag_btn}</button></div>
    <div class="br" style="margin-top:6px"><button class="btn" id="be" onclick="TE()">{edge_on}</button><button class="btn" onclick="PNGX()">{png_btn}</button></div>
    <button class="btn" style="margin-top:6px" onclick="RV()">{reset_btn}</button>
    <button class="btn" onclick="HELP()">{help_btn}</button>
  </div>
  <div id="dp"><div class="dph"><span class="dpt">{preview_label}</span><span><button class="dpbtn" id="bk" style="display:none">{back_btn}</button><button class="dpbtn" id="dpx" title="Esc">&#10005;</button></span></div><div id="dpc"><div class="de">{click_hint}</div></div></div>
  </div>
  <div id="sbt" onclick="TS()">&#9664;</div>
  <div id="nc">
    <div id="net"></div>
    <div id="load"><div class="spin"></div><span>{loading}</span></div>
    <div id="st"></div><div id="hint">{hint}</div>
    <div id="help"><div class="hcard"><h3>{help_title}</h3>{help_rows}<button class="btn hclose" onclick="HELP()">{close_btn}</button></div></div>
  </div>
</div>
<script>var D = {data};</script>
<script>{js}</script>
</body></html>"""


# ── UI strings ─────────────────────────────────────────────────────

def ui_strings(lang, title):
    if lang == 'zh':
        s = dict(
            title=title, view_label='布局视图', search_label='搜索',
            search_placeholder='搜索实体… (Ctrl+K)', filter_label='类型筛选（兼作图例，悬停可"仅看"）',
            controls_label='操作', fit_btn='适应窗口', drag_btn='拖拽', reset_btn='重置全部',
            edge_on='隐藏关系标签', png_btn='导出 PNG', help_btn='帮助 / 快捷键 (?)',
            close_btn='关闭', click_hint='点击节点或边查看详情', loading='正在生成布局…',
            hint='滚轮缩放 · 拖拽 · 单击详情 · 双击聚焦 · ? 帮助',
            help_title='快捷键',
            preview_label='知识预览', back_btn='← 返回',
            view_options=('<option value="force">力导向</option><option value="circular">环形</option>'
                          '<option value="type-circular">类型分区</option><option value="hub-spoke">中心辐射</option>'
                          '<option value="concentric">同心圆</option><option value="grid">网格</option>'
                          '<option value="hierarchical">层级</option>'),
            i18n=dict(nodes='节点', edges='关系', edgesLc='条关系', conf='置信度',
                      aliases='别名', source='来源', connections='关联', noconn='暂无关联',
                      clickhint='点击节点或边查看详情', drag='拖拽', locked='已锁定',
                      edgeOn='隐藏关系标签', edgeOff='显示关系标签',
                      only='仅看', isolate='只看邻域', showAll='显示全部'),
            help_rows=_help_rows([('Ctrl / ⌘ + K', '聚焦搜索框'), ('Enter（搜索中）', '定位首个匹配'),
                                  ('V', '切换布局'), ('L', '锁定 / 解锁位置'),
                                  ('F', '适应窗口'), ('B', '返回上一个节点'),
                                  ('双击节点 / 空白', '聚焦节点 / 适应窗口'),
                                  ('Esc', '取消选择 / 关闭'),
                                  ('? 或 H', '打开 / 关闭本帮助')]),
        )
    else:
        s = dict(
            title=title, view_label='Layout', search_label='Search',
            search_placeholder='Search entities… (Ctrl+K)', filter_label='Type filter (legend; hover for "only")',
            controls_label='Controls', fit_btn='Fit', drag_btn='Drag', reset_btn='Reset all',
            edge_on='Hide edge labels', png_btn='Export PNG', help_btn='Help / shortcuts (?)',
            close_btn='Close', click_hint='Click any node or edge', loading='Computing layout…',
            hint='Scroll zoom · drag · click details · dbl-click focus · ? help',
            help_title='Keyboard shortcuts',
            preview_label='Knowledge preview', back_btn='← Back',
            view_options=('<option value="force">Force-Directed</option><option value="circular">Circular</option>'
                          '<option value="type-circular">Type Arc</option><option value="hub-spoke">Hub-Spoke</option>'
                          '<option value="concentric">Concentric</option><option value="grid">Grid</option>'
                          '<option value="hierarchical">Hierarchical</option>'),
            i18n=dict(nodes='Nodes', edges='Edges', edgesLc='edges', conf='conf',
                      aliases='Aliases', source='Source', connections='Connections', noconn='No connections',
                      clickhint='Click any node or edge', drag='Drag', locked='Locked',
                      edgeOn='Hide edge labels', edgeOff='Show edge labels',
                      only='only', isolate='Isolate neighborhood', showAll='Show all'),
            help_rows=_help_rows([('Ctrl / ⌘ + K', 'Focus search'), ('Enter (in search)', 'Jump to first match'),
                                  ('V', 'Cycle layout'), ('L', 'Lock / unlock positions'),
                                  ('F', 'Fit to window'), ('B', 'Back to previous node'),
                                  ('Dbl-click node / empty', 'Focus node / fit'),
                                  ('Esc', 'Clear / close'),
                                  ('? or H', 'Toggle this help')]),
        )
    return s


def _help_rows(pairs):
    return ''.join('<div class="hrow"><kbd>%s</kbd><span>%s</span></div>' % (k, v)
                   for k, v in pairs)


# ── Main ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Generate an interactive KG viewer.')
    ap.add_argument('graph', help='Path to graph.json')
    ap.add_argument('--out', default=None, help='Output HTML path')
    ap.add_argument('--title', default='Knowledge Graph', help='Page title')
    ap.add_argument('--lang', default='auto', choices=['auto', 'en', 'zh'],
                    help='UI language; auto follows the graph\'s dominant script')
    args = ap.parse_args()

    with open(args.graph, encoding='utf-8') as f:
        graph = json.load(f)
    if 'entities' not in graph or 'relationships' not in graph:
        print("Error: graph.json must contain 'entities' and 'relationships'")
        sys.exit(1)

    lang = resolve_lang(graph, args.lang)
    data = build_data(graph, lang)
    ui = ui_strings(lang, args.title)
    data['i18n'] = ui.pop('i18n')

    data_json = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    html = HTML_TEMPLATE.format(css=CSS, js=JS_CODE, data=data_json, lang=lang, **ui)

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.graph)) or '.', 'graph.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated: {out_path}")
    print(f"  UI language: {lang}  ·  entities: {len(graph['entities'])}  "
          f"relationships: {len(graph['relationships'])}")


if __name__ == '__main__':
    main()
