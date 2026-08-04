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
3D geometry. It produces STEP files, PNG renders, mesh exports, and geometric
metrics. **All command output is structured JSON on stdout** (parse it as JSON);
human-readable progress and diagnostics go to **stderr**. The `bash` tool returns
`stdout` and `stderr` as separate fields — do NOT merge them with `2>&1` before
parsing JSON, or progress lines will break parsing.

## Environment check first

Before doing any work, confirm agentcad is callable:

```bash
agentcad --help
```

If the command is not found, ask the user for the correct command or PATH (e.g.
`/path/to/conda-env/Scripts/agentcad.exe`). Every command below assumes the
`agentcad` command resolves in the `bash` tool's environment.

## First-time setup

Pick a working directory for this design task. Every agentcad command must run
from **inside** a project directory that has an `agentcad.json`. The platform
`bash` tool takes a `working_directory` argument — use it (or an absolute path
in the command) instead of `cd`, since `cd && ...` chains are not allowed:

```bash
mkdir -p cad_output
agentcad init --name <project_name>    # run with working_directory=cad_output
agentcad --help                        # read the built-in guide and reference
```

`agentcad init` records build123d as the project runtime, so scripts need zero
imports (build123d primitives and helpers are pre-injected). CadQuery remains
available for existing projects via `--runtime cadquery`.

**Note on output paths:** `agentcad run` writes each version into a
directory whose prefix is the label of the *first* successful run and whose
suffix is the incremented version number — version 1 is just the label
(e.g. first run label `v1` → `v1/output.step`), and later versions append
`_v<version>` (e.g. `v1_v2/output.step`). **Always read the real paths from
the JSON response's `outputs.step`** rather than assuming a fixed directory.

## Core workflow

1. **Write a script.** No imports needed — build123d primitives (`Box`,
   `Cylinder`, `Sphere`, `Plane`), `show_object`, and agentcad edit helpers are
   pre-injected. `show_object(result)` is **required** (at least one call).

   ```python
   box = Box(10, 20, 5)
   show_object(box)
   ```

   Save it with `write_file`, e.g. `cad_output/model.py`.

2. **Dry-run first** to check metrics without consuming a version:

   ```bash
   agentcad run cad_output/model.py --output test --dry-run
   ```

   Check `volume`, `dimensions`, `is_valid` in the JSON response.

3. **Run for real.** Visual feedback is on by default:

   ```bash
   agentcad run cad_output/model.py --output v1
   ```

   Every successful run produces (paths are in the JSON response):
   - `preview.png` — 4-view composite (front, right, top, iso). **Read this**
     to confirm the part looks right before iterating.
   - `diff.side_by_side` — side-by-side PNG vs the most recent successful prior
     version. **Read this** when iterating to see what your change did.
   - `diff.overlay` — tinted (green prev, red this) overlay for subtle shifts.
   - `viewer.html` — interactive 3D review viewer for the user. The viewer,
     GLB, and diff PNGs always generate regardless of `--no-preview`.

   Pass `--no-preview` only for tight parametric sweeps where latency matters
   (it skips the composite render; STEP/GLB/viewer are still produced).

4. **Review with the user.** The generated viewer opens automatically. Use
   `agentcad view old.step new.step` for an explicit non-adjacent comparison.

5. **Inspect if invalid.** If `is_valid: false` or geometry looks wrong:

   ```bash
   agentcad inspect cad_output/v1/output.step
   ```

   (Use the `outputs.step` path returned by `run`.)

6. **Measure feature sizes.** For dimensions beyond top-level metrics:

   ```bash
   agentcad measure cad_output/v1/output.step
   ```

   Use this for hole diameters, cylindrical boss diameters, edge lengths,
   face areas, and full per-feature measurements with `--features`.

7. **Check explicit feature requirements.** If the prompt names measurable
   holes, bores, or cylindrical bosses, write them into `spec.json` before
   final handoff:

   ```json
   {"features":[{"name":"bolt_holes","type":"cylinder","diameter_mm":6,"count":4}]}
   ```

   Then run:

   ```bash
   agentcad check-spec cad_output/v1/output.step cad_output/spec.json
   ```

   Revise the CAD if `passed` is false. `status: success` only means the
   comparison ran; `passed` is the actual spec-check result.

8. **Iterate.** Fix the script, run with a new `--output` label. Use
   `agentcad diff 1 2` to compare versions.

## Script writing rules

- `show_object(result)` is required — at least one call.
- Pre-injected by default (no import needed): build123d primitives like `Box`,
  `Cylinder`, `Sphere`, `Plane`, plus `show_object`, `load_step`, `pick_face`,
  `pick_edge`, `fillet_edges`, `chamfer_edges`, `shell_faces`, `cut_pocket`,
  `boss`, `split_by_plane`, `replace_face`, `annular_boss`, `raise_annulus`.
- For imported STEP/BREP edits, `load_step(path)` returns a build123d `Part`:
  ```python
  base = load_step("vendor/output.step")
  solids = base.solids()
  faces = base.faces()
  edges = base.edges()
  bounds = base.bounding_box()
  ```
- For OCP internals (`gp_Pnt`, `BRepPrimAPI`, etc.), import manually.
- CadQuery compatibility remains available for existing projects — see
  `agentcad docs runtimes` for that separate workflow. Keep each script on ONE
  CAD API; agentcad reports the mismatch and the exact override if mixed.

## Key commands

| Command | Purpose |
|---------|---------|
| `agentcad init --name NAME` | Initialize project |
| `agentcad run SCRIPT --output LABEL` | Execute script, produce STEP + metrics |
| `agentcad run ... --dry-run` | Metrics only, no version consumed |
| `agentcad run ... --no-preview` | Suppress the 4-view composite preview (on by default) |
| `agentcad run ... --render iso,front` | PNG views |
| `agentcad run ... --export stl,glb,obj` | Mesh export |
| `agentcad run ... --params k=v,k=v` | Override script parameters |
| `agentcad render STEP --view SPEC` | Post-hoc renders with camera control |
| `agentcad export STEP --format stl,glb,obj` | Post-hoc mesh export |
| `agentcad measure STEP` | Dimensional report (overall metrics + feature sizes) |
| `agentcad check-spec STEP spec.json` | Pass/fail checklist against intended cylindrical features |
| `agentcad inspect STEP` | Topology report (validity, free edges) |
| `agentcad parts list REF` | List parts captured for a version |
| `agentcad parts show REF ID` | Show one versioned part by stable id |
| `agentcad parts view REF` | Hand off a part review viewer |
| `agentcad diff REF1 REF2` | Compare versions |
| `agentcad context` | Project state |
| `agentcad docs [SECTION]` | Runtime-aware built-in documentation |
| `agentcad view FILE [FILE_B]` | Open one model or explicit synchronized A/B comparison |

## Debugging playbook

1. **Check metrics first** — `volume` and `dimensions` catch most issues.
2. **Read `preview.png`** — the 4-view composite. Fastest way to spot problems.
3. **Read `diff.side_by_side`** if iterating — confirms your change did what
   you intended.
4. **Negative volume?** Wire winding is backwards (CW instead of CCW).
5. **Need a hole diameter or edge length?** Run `agentcad measure`.
6. **Need to verify explicit hole/bore counts?** Write `spec.json`, then run
   `agentcad check-spec`.
7. **`is_valid: false`?** Run `agentcad inspect` — check `free_edge_count` and
   shell status.
8. **Hollow shape?** `free_edge_count > 0` means open shell.
9. **Complex profiles (gears, splines)?** Use subtractive construction — cut
   from a blank cylinder/box instead of building up. See `agentcad docs patterns`.

## Patterns

- **Build at origin, then position:** Create geometry at origin, use
  `translate()` and `rotate()` to place it.
- **Compound vs fuse:** `Compound([...])` keeps assembly parts separate; use
  build123d's `+` operator to boolean-fuse solids.
- **Parametric scripts:** Top-level variable assignments become overridable via
  `--params`. Use this for iteration.
- **Named parts:** `show_object(shape, id="wheel_left", name="Left wheel",
  options={"color": "red"})` for stable part handles, per-part metrics, and
  colored GLB export.

## Deliverables

Report the final paths to the user: the STEP file, preview PNG, exported meshes
(STL/GLB), and the viewable `viewer.html`. Summarize key metrics (volume,
dimensions, validity) and any design assumptions made.

## Known issue: Chinese Windows encoding bug

On **Chinese Windows**, `agentcad run` may end with `status: error` and a
`UnicodeEncodeError: 'gbk' codec can't encode character ...` traceback while
writing `viewer.html`. **The STEP file, GLB, and preview.png are still
generated correctly** — only the viewer HTML write fails. Linux/macOS are
unaffected.

If you hit this:
1. Check whether `vN/output.step` exists and `agentcad measure` works on it. If
   yes, the model is good — report the STEP/preview as the deliverable and note
   the viewer.html issue.
2. Report the error to the user with the hint to apply the UTF-8 fix described
   in `docs/agentcad-部署说明.md` (a `sitecustomize.py` in the agentcad Python
   environment).
