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

**语言要求：无论用户输入什么语言，你给用户的最终回复、进度描述、设计说明、
尺寸报告，一律使用中文。** 只有 CAD 代码、文件路径、变量名保持英文。

You have access to **agentcad**, a CLI that turns build123d Python scripts into
3D geometry. agentcad is installed by `setup_agentcad.ps1` / `setup_agentcad.sh`
(see docs/agentcad-部署说明.md), but its **exact path varies by machine**. So the
FIRST thing you do is detect it — once. Do not assume a fixed path.

**Step 0 — detect agentcad (do this once, at the very start):**

```bash
python src/agent_platform/skills/cad-agentcad/scripts/find_agentcad.py
```

It prints JSON like `{"agentcad": "<path>", "agentcad_python": "<path>", ...}`.
From then on, every `agentcad` command below uses the detected path (the
`agentcad` field; or the `agentcad_python` path + `-m agentcad` if the CLI is
absent). If `agentcad` is empty, tell the user to run the setup script — do not
proceed.

Each tool call is expensive — keep the total under ~10 calls.

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

4. **Generate a measured viewer** so the frontend 3D viewer shows the
   Dimensions / Features / Validity / Cylindrical features panels. Without
   this, the Spec check button is greyed out and those panels are missing.
   **Do NOT use `agentcad view`** — it opens a browser window. Use the
   platform helper script instead (writes the viewer file, no browser).

   **IMPORTANT**: `make_viewer.py` imports the `agentcad` module, which only
   exists in the agentcad Python environment, NOT the platform's default
   `python`. Run it with the **`agentcad_python` path from Step 0** — it is
   already in **forward-slash** form (e.g. `D:/software/.../python.exe`), which
   the bash tool requires (backslashes get swallowed as escape chars). Do NOT
   substitute the bare `python` command, and do NOT retry with backslashes —
   both fail. Just replace `<agentcad_python>` with the detected value:

   ```bash
   <agentcad_python> src/agent_platform/skills/cad-agentcad/scripts/make_viewer.py <outputs.step path> --measure --out <viewer path>
   ```

   Example (run from the project root, `working_directory` unset):
   ```bash
   <agentcad_python> src/agent_platform/skills/cad-agentcad/scripts/make_viewer.py cad_output/v1/output.step --measure --out cad_output/v1/viewer_measured.html
   ```
   The script prints a JSON line `{"viewer": "<path>"}` on success. Report
   that path so the frontend can display it.

   This produces a viewer.html with measurement data embedded. Report its
   path (from the JSON `viewer` field) so the frontend can display it.

5. **Report** the STEP path and metrics to the user via `complete_task`.

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

### CRITICAL — build123d syntax that works (verified on agentcad v0.4)

These are the rules that make scripts run. **Do not deviate.** If you write
`from build123d import ...`, agentcad breaks — it pre-injects everything, so
**never write import statements for build123d**.

1. **No imports.** `Box`, `Cylinder`, `Sphere`, `Plane`, `Compound`, `Axis`,
   `fillet`, `chamfer` are pre-injected. Never write `from build123d import ...`.
2. **Fillet/chamfer use the TOP-LEVEL `fillet()` / `chamfer()` functions**, NOT
   `.fillet()` methods and NOT `fillet_edges`:
   ```python
   part = fillet(part.edges().filter_by(Axis.Z), 3)   # ✅ R3 on vertical edges
   part = chamfer(part.edges().filter_by(Axis.Z), 2)   # ✅ 2mm chamfer
   ```
3. **Holes = boolean subtraction with a `Cylinder`.** Position it, then subtract:
   ```python
   hole = Cylinder(12.5, 200).rotate(Axis.X, 90).translate((0, 0, 50))
   part = part - hole
   ```
4. **Counterbore/countersink = stack two cylinders and subtract both:**
   ```python
   for sx, sy in ((-40,-30), (40,-30), (-40,30), (40,30)):
       hole = Cylinder(8.5/2, 30).translate((sx, sy, -5))     # through hole
       cs   = Cylinder(16/2, 5).translate((sx, sy, 2.5))       # 16mm × 5mm counterbore
       part = part - hole - cs
   ```
5. **Assembly = boolean union with `+`.** Build pieces at origin, then
   `.translate()`:
   ```python
   base   = Box(120, 80, 15).translate((0, 0, 7.5))
   ear    = Box(15, 80, 70).translate((0, 20, 50))
   part   = base + ear + ear.mirror(Axis.Y)                  # symmetric second ear
   ```
6. **Mirror for symmetry:** `shape.mirror(Axis.X)` / `shape.mirror(Axis.Y)`
   mirrors across that axis (build123d method, works on a Shape).
7. **Ellipse (oval slot) = build from an elliptical Sketch or approximate with
   cylinders + box:** for an oval hole, union two cylinders and a box then
   subtract:
   ```python
   oval = (Cylinder(10, 30).translate((0, 10, 0)) + Cylinder(10, 30).translate((0, -10, 0))
           + Box(20, 20, 30)).rotate(Axis.X, 90).translate(...)
   part = part - oval
   ```
8. **Always end with `show_object(part)`.**

### Complete worked example — robot fork joint bracket (verified)

```python
# 机器人关节连接叉座 Fork Joint Bracket
L = 120.0  # mm 底座长
W = 80.0   # mm 底座宽
H = 15.0   # mm 底座厚
ear_t = 15.0   # mm 耳厚
ear_h = 70.0   # mm 耳高
gap = 40.0     # mm 两耳间距
bore_dia = 25.0  # mm 旋转轴孔

base = Box(L, W, H).translate((0, 0, H/2))
ear1 = Box(ear_t, W, ear_h).translate((0, gap/2, H + ear_h/2))
ear2 = Box(ear_t, W, ear_h).translate((0, -gap/2, H + ear_h/2))
part = base + ear1 + ear2

# 旋转轴孔 贯穿 (同轴, 孔心距底座顶 50mm)
bore = Cylinder(bore_dia/2, 200).rotate(Axis.X, 90).translate((0, 0, H + 50))
part = part - bore

# 底部 4 个沉头安装孔 (8.5 通孔 + 16 沉头 x 5 深)
for sx in (-40, 40):
    for sy in (-30, 30):
        hole = Cylinder(8.5/2, 30).translate((sx, sy, -5))
        cs   = Cylinder(16/2, 5).translate((sx, sy, 2.5))
        part = part - hole - cs

# 所有外部竖边 圆角 R3
part = fillet(part.edges().filter_by(Axis.Z), 3)

show_object(part)
```

Follow this structure for any multi-feature part: build base → add ears/features
via `+` → subtract holes via `-` → fillet/chamfer edges → `show_object`.


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

## Reporting for frontend display

When you call `complete_task`, **always** include the generated `viewer.html`
path in `detail` so the frontend can display the 3D model. Format it as a clear
line:

```
VIEWER_PATH: <path-to-viewer.html>
```

Use the **actual path** from the `agentcad run` JSON `viewer` field (e.g.
`cad_output/v1/viewer.html`). If the run failed on Chinese Windows but the
viewer.html exists, still report its path. The frontend renders this viewer
inside the chat automatically; the user should not have to open files manually.

