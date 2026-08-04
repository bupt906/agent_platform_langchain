---
name: cad-agentcad
description: >-
  CAD tool for AI agents, powered by the agentcad CLI. Use when the user asks
  you to design, model, or build a 3D object, mechanical part, bracket,
  enclosure, gear, or any parametric 3D shape. agentcad executes build123d
  Python scripts (CadQuery compatibility available) and produces STEP files,
  PNG renders, mesh exports (STL/GLB/OBJ), geometric metrics, validation,
  version diffing, and browser preview. Triggers include phrasings like
  "design a bracket", "create a 3D model", "make a mechanical part", "generate
  a STEP file", "CAD this shape". This skill is for 3D CAD generation ONLY —
  not for 2D drafting, mesh editing, or simulation.
tools: [read_file, write_file, bash]
complete_tool: complete_task
---

# CAD Generation with agentcad

You have access to **agentcad**, a CLI that turns build123d Python scripts into
3D geometry. **agentcad is already installed and configured.** Do NOT probe the
environment, do NOT run `which`, `where`, or write probe files. Just execute the
steps below. Each tool call is expensive — keep the total under ~10 calls.

**Golden rule — this is the whole workflow:**

1. **Write a `.py` script** with `write_file`. Scripts need zero imports — build123d
   primitives (`Box`, `Cylinder`, `Sphere`, `Plane`) and helpers are pre-injected.
   **The file MUST end in `.py`** (`write_file` supports `.py`). Always call
   `show_object(result)` at least once.

   ```python
   box = Box(10, 20, 5)
   show_object(box)
   ```

2. **Init the project** (once per working directory). Do NOT use `cd` or `&&` —
   both are forbidden by the `bash` tool. Run `mkdir` and `agentcad init` as two
   **separate** `bash` calls, each with `working_directory` set to the project
   folder:

   ```bash
   mkdir -p cad_output                          # working_directory=<parent>
   agentcad init --name <project_name>          # working_directory=cad_output
   ```

3. **Run the script** with `bash` (same `working_directory=cad_output`):

   ```bash
   agentcad run model.py --output v1
   ```

   The JSON response contains `outputs.step` (the STEP path), `metrics`
   (`volume`, `dimensions`, `is_valid`), and `preview`. Use the **actual paths
   from the JSON** — do not guess.

4. **Report** the STEP path and metrics to the user via `complete_task`.

**Forbidden (will error — do not try):**
- `cd`, `&&`, `||`, `;`, pipes, `>` — the `bash` tool rejects chained commands.
- `python -c "..."` or `python < .txt` — the `bash` tool rejects Python `-c`.
- `rm`, `del`, `which`, `where`, `pwd` — not whitelisted.
- Writing the CAD script with a non-`.py` extension — `agentcad` only runs `.py`.

That is the minimum viable path. Use the command reference below only when the
user asks for more (renders, mesh export, measurements, inspection).

## Command reference

All commands output JSON on **stdout**; progress goes to **stderr**. The `bash`
tool returns them separately — do NOT merge with `2>&1`.

| Command | Purpose |
|---------|---------|
| `agentcad init --name NAME` | Initialize a project (creates `agentcad.json`) |
| `agentcad run SCRIPT.py --output LABEL` | Execute script → STEP + metrics + preview |
| `agentcad run ... --dry-run` | Metrics only, no version consumed |
| `agentcad run ... --export stl,glb,obj` | Mesh export for 3D printing |
| `agentcad run ... --render iso,front` | Extra PNG views |
| `agentcad run ... --params k=v` | Override a script's top-level variables |
| `agentcad measure STEP` | Dimensional report (volume, feature sizes, hole diameters) |
| `agentcad inspect STEP` | Topology report (validity, free edges) |
| `agentcad diff REF1 REF2` | Compare two versions |
| `agentcad docs [SECTION]` | Built-in documentation |

## Script writing rules

- The file **must end in `.py`** (e.g. `model.py`). agentcad only runs `.py`
  scripts.
- `show_object(result)` is **required** — at least one call. Without it there is
  nothing to export.
- No imports needed: `Box`, `Cylinder`, `Sphere`, `Plane`, `Compound`, and
  edit helpers (`load_step`, `fillet_edges`, `chamfer_edges`, `shell_faces`,
  `cut_pocket`, `boss`, `split_by_plane`) are pre-injected.
- Booleans use Python operators: `plate - hole`, `A + B`, `A & B`.
- Build at origin, then `translate()` / `rotate()` to position.
- Keep each script on ONE CAD API (build123d by default; CadQuery only for
  existing projects via `--runtime cadquery`).

## Debugging

1. `volume`, `dimensions`, `is_valid` in the run JSON catch most issues.
2. **Negative volume?** Wire winding is backwards (CW instead of CCW).
3. **`is_valid: false`?** Run `agentcad inspect <step>` — check `free_edge_count`.
4. **Need a hole diameter?** Run `agentcad measure <step>`.
5. **Complex profiles (gears)?** Use subtractive construction — cut from a blank
   cylinder/box instead of building up.

## Known issue: Chinese Windows encoding

On Chinese Windows, `agentcad run` may end `status: error` with a
`UnicodeEncodeError: 'gbk'` traceback while writing `viewer.html`. **The STEP,
GLB, and preview are still generated** — only the HTML viewer fails. If this
happens, check whether `outputs.step` exists and `agentcad measure` works on it;
if yes, the model is good, report it, and mention the viewer.html issue. See
`docs/agentcad-部署说明.md` for the permanent fix.
