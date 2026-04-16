---
name: cli-anything
description: "Use any supported GUI application (GIMP, Blender, LibreOffice, Audacity, OBS, etc.) on behalf of the user. Auto-installs the app and CLI harness, then executes the task directly."
action-sets: ["shell", "file_operations"]
---

# CLI-Anything Skill

**Core rule: Do everything yourself. Never give the user a command to run. Never explain steps. Just execute the task and report the result.**

---

## FORBIDDEN — Never Do These (causes bugs on all platforms)

These patterns are strictly banned. If you catch yourself about to do any of these, stop and use the cli-anything harness instead.

| ❌ FORBIDDEN | ✅ CORRECT |
|---|---|
| `soffice.exe --headless --convert-to pdf ...` | `cli-anything-libreoffice convert doc.docx output.pdf` |
| `cd "C:\Program Files\LibreOffice\program" && soffice.exe ...` | `cli-anything-libreoffice convert doc.docx output.pdf` |
| `gimp --batch-interpreter=script-fu-use-v2 ...` | `cli-anything-gimp image resize input.jpg output.jpg 1920 1080` |
| `blender --background scene.blend --render-output ...` | `cli-anything-blender render scene.blend --output frames/ --format PNG` |
| `inkscape --export-type=png logo.svg` | `cli-anything-inkscape export logo.svg logo.png --dpi 300` |
| Chaining with `&&`: `cmd1 && cmd2` | Two separate `run_shell` calls |
| Any `.exe` extension in a command | No `.exe` — harness is cross-platform |
| Hardcoded paths like `C:\Program Files\...` | Use the harness — it finds the app automatically |

**Why these are banned:**
- `.exe` only exists on Windows — breaks on macOS and Linux
- `C:\Program Files\...` paths break on macOS and Linux
- `&&` chaining breaks in PowerShell on Windows
- Raw app CLIs require knowing app-specific flags — the harness handles all of that

---

## Help Response (no tools needed — just reply with text)

If the user's message matches any of these (case-insensitive, any wording):
- "cli anything help" / "cli-anything help" / "cli help"
- "what apps does cli-anything support" / "what can cli-anything do"
- "show cli apps" / "cli anything guide" / "list cli apps"
- Any variation asking what CLI-Anything can do or which apps are supported

**Do not run any tools. Reply directly with this message:**

---

**CLI-Anything — What I Can Do**

Just tell me what you want done in plain English. I'll auto-install the app if it's not on your system and complete the task for you — you never need to run any commands yourself.

**Creative & Media**
| App | What I can do | Example prompt |
|---|---|---|
| GIMP | Resize, crop, blur, convert, export images | "Resize photo.jpg to 1920×1080 and save as photo_hd.jpg" |
| Blender | Render 3D scenes, run scripts, export models | "Render scene.blend to PNG frames in the frames/ folder" |
| Inkscape | Export SVG to PNG/PDF, convert vector files | "Export logo.svg as a 300 DPI PNG" |
| Krita | Export paintings, batch convert images | "Export painting.kra as PNG" |
| Audacity | Trim, export, convert audio files | "Trim the first 30 seconds from audio.mp3 and save as clip.mp3" |
| OBS Studio | Record screen, stream | "Record my screen for 60 seconds" |
| Kdenlive | Render video projects to MP4/MKV | "Render project.kdenlive to MP4" |
| Shotcut | Render video projects to MP4 | "Render project.mlt to MP4" |

**Office & Productivity**
| App | What I can do | Example prompt |
|---|---|---|
| LibreOffice | Convert DOCX/XLSX/PPTX to PDF, run macros | "Convert report.docx to PDF" |
| Mubu | Manage knowledge outlines | "Open my outline in Mubu" |

**Communication**
| App | What I can do | Example prompt |
|---|---|---|
| Zoom | Start/join meetings | "Start a Zoom meeting" |

**Diagramming**
| App | What I can do | Example prompt |
|---|---|---|
| Draw.io | Export diagrams to PNG/SVG/PDF | "Export diagram.drawio as PNG" |
| Mermaid | Render diagram code to PNG | "Render this diagram to PNG: graph TD; A-->B; B-->C" |

**AI & ML**
| App | What I can do | Example prompt |
|---|---|---|
| ComfyUI | Run AI image generation workflows | "Run workflow.json and save images to output/" |
| AnyGen | Generate AI content | "Generate content using AnyGen" |
| NotebookLM | AI research and summarization | "Summarize this PDF using NotebookLM" |
| Ollama | Run local LLM inference | "Run llama3 and summarize this text: ..." |
| Stable Diffusion | Generate images from text prompts | "Generate 'a sunset over mountains' and save as out.png" |

**Dev & Infrastructure**
| App | What I can do | Example prompt |
|---|---|---|
| JupyterLab | Execute notebooks, save output | "Execute notebook.ipynb and save the output" |
| Grafana | Export dashboards | "Export my dashboard as JSON" |
| Gitea | Create repos, manage git hosting | "Create a private repo called myrepo on Gitea" |
| GitLab | Create projects, manage CI/CD | "Create a new project on GitLab" |
| NextCloud | Sync files, manage cloud storage | "Sync my files to NextCloud" |
| Jenkins | Trigger build pipelines | "Trigger my build pipeline" |
| AdGuard Home | Set up network-wide ad blocking | "Set up network-wide ad blocking with AdGuard Home" |

**GIS & 3D Design**
| App | What I can do | Example prompt |
|---|---|---|
| FreeCAD | Export 3D models to STL/STEP | "Export model.fcstd as STL" |
| QGIS | Export maps to PNG/PDF | "Export map.qgz as PNG" |

**Tips:**
- Always give me the full file path (e.g. `C:\Users\you\Desktop\photo.jpg`)
- If the app isn't installed, I'll install it automatically — just wait a few minutes
- I never ask you to run commands yourself — I do everything for you
- Works on Windows, macOS, and Linux

---

## Supported Apps Reference

Use this table to look up the correct names for every step.

| App | cli-hub name | Windows (winget) | macOS (brew cask) | Linux (apt) |
|---|---|---|---|---|
| GIMP | `gimp` | `GIMP.GIMP` | `gimp` | `gimp` |
| Blender | `blender` | `BlenderFoundation.Blender` | `blender` | `blender` |
| Inkscape | `inkscape` | `Inkscape.Inkscape` | `inkscape` | `inkscape` |
| Audacity | `audacity` | `Audacity.Audacity` | `audacity` | `audacity` |
| OBS Studio | `obs` | `OBSProject.OBSStudio` | `obs` | `obs-studio` |
| Kdenlive | `kdenlive` | `KDE.Kdenlive` | `kdenlive` | `kdenlive` |
| Shotcut | `shotcut` | `Meltytech.Shotcut` | `shotcut` | `shotcut` |
| Krita | `krita` | `KDE.Krita` | `krita` | `krita` |
| LibreOffice | `libreoffice` | `TheDocumentFoundation.LibreOffice` | `libreoffice` | `libreoffice` |
| Mubu | `mubu` | _(web app — skip winget)_ | _(web app)_ | _(web app)_ |
| Zoom | `zoom` | `Zoom.Zoom` | `zoom` | `zoom` |
| Draw.io | `draw-io` | `JGraph.Draw` | `drawio` | _(AppImage)_ |
| Mermaid | `mermaid` | `OpenJS.NodeJS` _(then npm i -g @mermaid-js/mermaid-cli)_ | `mermaid` | _(npm)_ |
| ComfyUI | `comfyui` | _(git clone — see below)_ | _(git clone)_ | _(git clone)_ |
| AnyGen | `anygen` | _(pip install)_ | _(pip install)_ | _(pip install)_ |
| NotebookLM | `notebooklm` | _(web app — Playwright)_ | _(web app)_ | _(web app)_ |
| Ollama | `ollama` | `Ollama.Ollama` | `ollama` | _(curl install)_ |
| AdGuard Home | `adguard-home` | `AdGuard.AdGuardHome` | `adguard-home` | _(binary release)_ |
| Stable Diffusion | `stable-diffusion` | _(git clone AUTOMATIC1111)_ | _(git clone)_ | _(git clone)_ |
| JupyterLab | `jupyterlab` | _(pip install jupyterlab)_ | _(pip install)_ | _(pip install)_ |
| FreeCAD | `freecad` | `FreeCAD.FreeCAD` | `freecad` | `freecad` |
| QGIS | `qgis` | `OSGeo.QGIS` | `qgis` | `qgis` |
| Grafana | `grafana` | `GrafanaLabs.Grafana` | `grafana` | `grafana` |
| Gitea | `gitea` | `Gitea.Gitea` | `gitea` | _(binary)_ |
| GitLab | `gitlab` | _(docker or package)_ | _(docker)_ | `gitlab-ce` |
| NextCloud | `nextcloud` | `Nextcloud.NextcloudDesktop` | `nextcloud` | _(snap/docker)_ |
| Jenkins | `jenkins` | `Jenkins.Jenkins` | `jenkins` | `jenkins` |

---

## Execution Flow (follow every time — use EXACT timeouts listed)

**CRITICAL: Always pass the timeout shown below to run_shell. Never use the default (30s). winget/brew installs take minutes — without a timeout they die silently and the agent loops forever.**

**CRITICAL: Never chain commands with `&&` or `;` in a single run_shell call. Use one separate run_shell call per command.**

### Step 1 — Detect OS
Run with `timeout: 10`:
```
python -c "import platform; print(platform.system())"
```
Result: `Windows`, `Darwin`, or `Linux`.

### Step 2 — Check if the app is installed
Run with `timeout: 10`:
```
gimp --version
```
(replace with the correct app: `blender --version`, `libreoffice --version`, etc.)

- Exit 0 → already installed → skip to Step 4
- Exit non-zero → not installed → go to Step 3

### Step 3 — Install the app (ONE attempt only — never retry install)

**Windows** — run with `timeout: 600`:
```
winget install --id <WingetID> --silent --accept-package-agreements --accept-source-agreements
```

**macOS** — run with `timeout: 600`:
```
brew install --cask <cask-name>
```

**Linux** — run with `timeout: 300`:
```
sudo apt-get install -y <package>
```

**Special cases:**
- ComfyUI / Stable Diffusion: `git clone` + `pip install -r requirements.txt` — `timeout: 600`
- Mermaid: `npm install -g @mermaid-js/mermaid-cli` — `timeout: 120`
- JupyterLab / AnyGen: `pip install <package>` — `timeout: 120`
- Web apps (Mubu, NotebookLM): no install needed — use `playwright-mcp`
- Ollama on Linux: `curl -fsSL https://ollama.com/install.sh | sh` — `timeout: 300`

After install, re-run Step 2 check once (`timeout: 10`). If still fails → tell the user, stop completely.

### Step 4 — Check if CLI harness is installed
Run with `timeout: 10`:
```
cli-anything-<appname> --version
```
- Found → skip to Step 6
- Not found → go to Step 5

### Step 5 — Install CLI harness (ONE attempt only)

**Always try CLI-Hub first** — run with `timeout: 120`:
```
pip install cli-anything-hub --quiet
```
Then run with `timeout: 120`:
```
cli-hub install <cli-hub-name>
```
(Two separate run_shell calls — do NOT chain with &&)

If CLI-Hub fails → generate a minimal harness with `write_file` (a Click CLI wrapping the app's real scripting API), then run with `timeout: 60`:
```
pip install -e cli_anything/<appname> --quiet
```

If harness install also fails → tell the user, stop completely.

### Step 6 — Execute the user's task using the CLI harness ONLY

**MANDATORY: Use ONLY `cli-anything-<app>` commands. Never call soffice, gimp, blender, or any app binary directly.**

Run with `timeout: 300` (or `timeout: 600` for renders/exports):

```
# Image editing — GIMP
cli-anything-gimp image resize input.jpg output.jpg 1920 1080
cli-anything-gimp filter blur input.jpg --radius 3 --output out.jpg
cli-anything-gimp export input.xcf output.png

# 3D / rendering — Blender
cli-anything-blender render scene.blend --output frames/ --format PNG
cli-anything-blender script run myscript.py scene.blend

# Vector — Inkscape
cli-anything-inkscape export logo.svg logo.png --dpi 300
cli-anything-inkscape convert input.svg output.pdf

# Painting — Krita
cli-anything-krita export painting.kra output.png

# Audio — Audacity
cli-anything-audacity trim audio.mp3 output.mp3 --start 0 --end 30
cli-anything-audacity export-mp3 project.aup3 output.mp3

# Video — Kdenlive / Shotcut
cli-anything-kdenlive render project.kdenlive output.mp4
cli-anything-shotcut render project.mlt output.mp4

# Office — LibreOffice (NEVER use soffice.exe directly)
cli-anything-libreoffice convert doc.docx output.pdf
cli-anything-libreoffice convert spreadsheet.xlsx output.pdf
cli-anything-libreoffice calc run macro.py spreadsheet.xlsx

# Diagrams
cli-anything-draw-io export diagram.drawio output.png
cli-anything-mermaid render diagram.mmd output.png

# AI / ML
cli-anything-comfyui run workflow.json --output images/
cli-anything-ollama run llama3 --prompt "summarize this"
cli-anything-stable-diffusion generate "a sunset over mountains" --output out.png

# Dev / Infra
cli-anything-jupyterlab execute notebook.ipynb --output result.ipynb
cli-anything-grafana export-dashboard my-dashboard dashboard.json
cli-anything-gitea create-repo myrepo --private

# GIS / Design
cli-anything-freecad export model.fcstd output.stl
cli-anything-qgis export map.qgz output.png
```

**Always run the task. Never print commands and ask the user to run them.**

If the task command fails → retry once with adjusted args. If it fails again → report the error and stop.

### Step 7 — Report result
One or two sentences only:
> "Done — rendered `output.mp4` from your Kdenlive project."
> "Converted `report.docx` to PDF at `report.pdf`."

---

## Hard Stop Rules (prevents infinite loops)

- **Never retry an install** — if `winget install` or `cli-hub install` fails, stop and tell the user.
- **Never loop on a timeout** — if a command times out once, it will time out again. Stop immediately.
- **Max 1 retry on the task command (Step 6) only** — not on installs.
- **If stuck after 3 total run_shell calls** for the same step → stop, tell the user what failed.
- **Never use `&&` or `;` to chain commands** — always use separate run_shell calls.
- **Never use `.exe` extensions** — use the cli-anything harness which is cross-platform.
- **Never hardcode app installation paths** — use the harness, it resolves the path automatically.