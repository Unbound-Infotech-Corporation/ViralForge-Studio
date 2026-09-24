# TrendForge Studio

Local Windows desktop app that turns **currently trending topics** into a **YouTube channel**: Shorts, standard and long videos, and multi-episode narrated docuseries. Native PySide6 UI. No paid API is required for core features.

Cinematic clips use **ViralForge Cinema** (Wan 2.2 and CogVideoX weights on disk). If those weights are missing, Studio **refuses the export** instead of publishing a title-card stand-in. **Quick Explainer** is the intentional CPU path: a real H.264 MP4 with voiceover, captions, music, intro/outro, and a YouTube pack (titles, description, pinned comment, community post).

## What you get

1. **First-run setup** — detects GPU, saves your channel voice, and **downloads every local model this PC can run** that you leave checked (Piper voices, Whisper, Ollama script models).
2. **Discover** — YouTube trending (via yt-dlp), Google Trends, Reddit, news RSS, movies/TV threads, custom search.
3. **Create** — Format / Model / Style / Voice dropdowns (VRAM, disk, and speed in the model label). Topic or YouTube URL → script → clips → stitch → YouTube-ready MP4.
4. **Channel** — name, niche, audience, subscribe CTA, brand voice, flagship series name. Used in outros, thumbnails, and sidecars.
5. **Projects / Gallery** — save/load, resume, regenerate a single shot, history of outputs.
6. **Models & Settings** — same installer as setup, plus connection URLs, Ollama script-model dropdown, theme, logs.

## Requirements (Windows)

| Piece | Required? | Notes |
| --- | --- | --- |
| Windows 10/11 x64 | Yes | |
| Python **3.11 or 3.12** (3.10–3.14 also work) | Yes (source install) | 3.12 is the sweet spot |
| NVIDIA GPU | No for Quick Explainer | **6 GB+ VRAM** for Wan / CogVideoX |
| ffmpeg | Strongly recommended | `imageio-ffmpeg` is bundled as fallback |
| [Ollama](https://ollama.com/download) | No | Local Script AI. Install + keep running, then the wizard pulls `qwen2.5:7b` / `14b`. No cloud API key. |
| ComfyUI | No | Optional if you already have a T2V workflow |

## Exact install (source, recommended)

Open **PowerShell**:

```powershell
# 1. Python 3.12 (preferred). 3.11 and 3.14 also work.
winget install Python.Python.3.12

# 2. ffmpeg on PATH (optional but better than the bundled copy)
winget install Gyan.FFmpeg

# 3. Clone / enter this repo
cd F:\ViralForge\VisualCreatorUnbound

# 4. Virtualenv + dependencies
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1

# 5. Launch
.\run.bat
```

Manual equivalent:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

First launch opens a setup wizard: hardware → channel kit → **Install models**. Every model this GPU/RAM can run is pre-checked. Click **Install selected models**. Ollama rows need Ollama already running (the wizard will not pop UAC or launch installers). You can finish setup and install the rest later under **Models & Settings → Install models**.

### Job Console

Produce progress opens in the **Job Console** (on by default; uncheck **Show when Produce starts** inside the panel).

- **View → Job Console**
- Status-bar **Console** button
- **Ctrl+`**

The first launch shows a hint bar until you dismiss it.

### Script Lab and Script AI

**Script Lab** is under **Produce**. It is an in-app browser for Grok, ChatGPT, Claude, and a research tab. Import a selection into the episode script Create uses. The browser needs Qt WebEngine (`pip install PySide6-Addons`). Paste-import and Script AI still work without it.

**Settings → Script AI** (also **Models → Script AI**) stores a bring-your-own API key for outlines, shot lists, dialogue, and virtual meeting notes. A chat-site subscription is not an API key. The default provider is local **Ollama** (**Models & Settings → Script model**); that path does not need a cloud key.

### CogVideoX and Wan

Put checkpoints in the cinema models folder (default `F:\TrendForge\models\cinema`, editable under **Models → Connection → Cinema models folder**):

| Model | Folder |
| --- | --- |
| CogVideoX | `cogvideox` |
| Wan 2.2 TI2V-5B | `wan2.2-ti2v-5b` |
| Wan 2.2 A14B | `wan2.2-i2v` |

Create lists **CogVideoX** directly beside the Wan rows. Legacy engines stay off that list. If the weights are missing, Generate stops with **Export refused** and does not write a card or silent `final.mp4`.

### Optional: Ollama

```powershell
winget install Ollama.Ollama
```

Keep Ollama running, then let TrendForge pull `qwen2.5:7b` (and `14b` on high-RAM PCs) from the setup installer. Manual pull still works: `ollama pull qwen2.5:7b`.

### Optional: ComfyUI

Run ComfyUI on `http://127.0.0.1:8188`. Export an API workflow to `trendforge/assets/comfy/t2v_workflow.json` (see the README in that folder).

## First video in minutes (no GPU models)

1. Create tab
2. **Format:** YouTube Short (or Standard video)
3. Topic: anything, e.g. `Why this movie is everywhere`
4. **Model:** Auto, or **Quick Explainer (works immediately)**
5. **Voice:** Windows SAPI, or Piper if setup installed it
6. **Generate Short** / **Generate Video**

For a flagship series: **Format → Plan a full docuseries season** → pick an episode row → **Generate episode**.

Output lands in:

`%LOCALAPPDATA%\TrendForge\TrendForge Studio\projects\<id>\output\final.mp4`

Sidecars: `youtube_description.txt`, `titles.txt`, `pinned_comment.txt`, `community_post.txt`, `end_screen.txt`, `tags.txt`, `thumb.jpg`, `captions/captions.srt`. Season plans also write `season_bible.txt`.

## Formats

| Format | Aspect | Length | Use |
| --- | --- | --- | --- |
| YouTube Short | 9:16 | 15–60s | Daily hooks, new subscribers |
| Standard video | 16:9 | 3–8 min | Workhorse upload |
| Long video | 16:9 | 10–18 min | Search / binge sessions |
| Docuseries episode | 16:9 | 18–40 min | Narrated investigation + cliffhanger |
| Plan a season | — | 4–6 briefs | Outline first, then generate each episode |

## Model dropdown (VRAM / speed / quality)

Each row in Create → Model shows **VRAM · disk · speed**. Switch anytime; last choice is remembered.

| Option | VRAM | Disk (approx) | Speed | Quality | When to use |
| --- | --- | --- | --- | --- | --- |
| Auto | — | — | — | — | ViralForge Cinema, or Quick Explainer without a suitable GPU. |
| Quick Explainer | 0 | ~0 | Fast | Good explainer | First run, laptops, CPU. Intentional cards. |
| ViralForge Cinema | model | weights on disk | Slow | Highest | Wan / CogVideoX. Refuses card stand-ins. |
| Wan 2.2 TI2V-5B | ~10 GB | ~12 GB | Medium | High | Folder `wan2.2-ti2v-5b` |
| CogVideoX | ~12 GB | ~20 GB | Medium | High | Folder `cogvideox`, listed beside Wan |
| Wan 2.2 A14B | 16+ GB | ~28 GB | Slow | Highest | Folder `wan2.2-i2v` |

Paid / cloud options (Edge TTS) stay **disabled** until you tick **Enable optional free-cloud fallbacks** in Settings.

## YouTube encode

Final MP4 is H.264 `yuv420p`, AAC 192 kbps, `+faststart` (H.265 optional in settings via `codec: h265` in `settings.json`). That matches typical YouTube upload guidance.

## Build a Windows exe / installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

- Folder build: `dist\TrendForgeStudio\TrendForgeStudio.exe`
- Inno Setup: open `installer\trendforge.iss` (after the PyInstaller build)

Nuitka alternative (optional, not default):

```powershell
.\.venv\Scripts\python.exe -m pip install nuitka
.\.venv\Scripts\python.exe -m nuitka --standalone --windows-console-mode=disable --plugin-enable=pyside6 run.py
```

## Project layout

```
trendforge/
  app.py                 # Qt entry
  domain/                # models, catalog, enums
  services/              # trends, cinema, Ollama, stitch, pipeline, installer
  ui/                    # PySide6 windows / pages
  plugins/               # drop-in backend registry
  assets/                # Comfy workflow stub, icons, music
scripts/                 # install + PyInstaller
installer/               # Inno Setup
tests/
```

Add a new video model: extend `trendforge/domain/catalog.py` (`hidden=False` to show it on Create). Add a whole backend: implement `trendforge/plugins/base.py` and register it in `trendforge/plugins/__init__.py`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Ollama pull failed | Install Ollama, keep it running, retry Install models. The local provider needs no API key. |
| Script Lab browser missing | `pip install PySide6-Addons`, then restart. Paste-import still works. |
| Script AI failed | Chat logins are not API keys. Set provider, key, and model under Settings → Script AI. |
| Export refused | Weights missing or the soundtrack is silent. Add CogVideoX/Wan files, or pick Quick Explainer. |
| Job Console | View → Job Console, status-bar Console, or Ctrl+` |
| CUDA OOM | Use Wan 5B, CogVideoX if it fits, or Quick Explainer; close other GPU apps |
| Empty Discover | Network/firewall; Search still works |
| No voice | Pick Piper after setup, or Windows Settings → Speech |
| ffmpeg errors | `winget install Gyan.FFmpeg` |
| Long job interrupted | **Resume** skips completed shots |

**Help → Copy logs** (or Models & Settings → Copy logs). Logs live under `%LOCALAPPDATA%\TrendForge\TrendForge Studio\logs\` (plus platformdirs log dir). Nothing is uploaded.

## Tests / smoke

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe run.py --smoke --offscreen
```

## License

MIT. Wan, CogVideoX, and other model weights keep their own licenses — respect those if you use them.
