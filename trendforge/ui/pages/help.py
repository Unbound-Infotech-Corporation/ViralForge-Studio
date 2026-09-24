from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QTextBrowser, QVBoxLayout, QWidget

GETTING_STARTED = """
<h1>Getting Started</h1>
<p>TrendForge Studio is a <b>local Windows app</b>. Core features never require a paid API.</p>
<ol>
<li>Finish the first-run wizard. It saves your channel voice and <b>downloads every local model this PC can run</b> that you leave checked (Piper narration, Whisper, Ollama scripts, Maestro cinematic weights when Maestro is already Started).</li>
<li>On <b>Create</b>, pick a <b>Format</b> from the dropdown: YouTube Short, standard video, long video, docuseries episode, or plan a season.</li>
<li>Leave <b>Model</b> on Auto, or pick one — each row shows VRAM, disk, and speed.</li>
<li>Click <b>Generate</b>. Wait for Research → Script → Generate → Stitch → Finalize.</li>
<li>Open <b>Gallery</b> for <code>final.mp4</code> plus titles, pinned comment, community post, and description files.</li>
</ol>
<p><b>Channel</b> stores your name, niche, CTA, and brand voice so outros and YouTube sidecars stay consistent.</p>
<p>Quick Explainer produces a real explainer MP4 with voice, captions, and music using ffmpeg + Windows SAPI or Piper.
That is the “works in minutes” path. Cinematic AI video needs Maestro running.</p>
"""

FORMAT_GUIDE = """
<h1>Formats that grow a channel</h1>
<ul>
<li><b>YouTube Short (9:16)</b> — 15–60s pattern interrupt. Post often. End card points to the long video.</li>
<li><b>Standard video (16:9)</b> — 3–8 min workhorse upload. Hook, context, takeaway, subscribe.</li>
<li><b>Long video</b> — 10–18 min session. Better for search and binge watch time.</li>
<li><b>Docuseries episode</b> — 18–40 min narrated investigation with cold open, evidence, cliffhanger.</li>
<li><b>Plan a season</b> — writes 4–6 episode briefs and a bible. Select a row, then Generate episode.</li>
</ul>
<p>Switch models anytime with the Model dropdown. Piper voices appear after setup installs them.</p>
"""

MODEL_GUIDE = """
<h1>Model Guide</h1>
<p>First-run setup and <b>Models &amp; Settings → Install models</b> download the free local stack. Large cinematic weights are queued inside Maestro when it is running. TrendForge will not launch installers or UAC prompts.</p>
<ul>
<li><b>Auto</b> — Maestro Director if reachable, else ComfyUI, else Quick Explainer.</li>
<li><b>Quick Explainer</b> — motion-graphics cards. 0 GB VRAM. Use this on first install.</li>
<li><b>Maestro Director</b> — best quality. Keep Maestro running via <code>start_maestro.bat</code> (Pinokio not required).</li>
<li><b>LTX-2.5 distilled</b> — fast cinematic + synced audio on ~8 GB.</li>
<li><b>Wan 2.2 TI2V-5B</b> — lighter Wan. Prefer under 12 GB.</li>
<li><b>Wan 2.2 A14B</b> — 16 GB+ recommended.</li>
<li><b>MiniMax H3</b> — dialogue / longer windows, ~12 GB+.</li>
<li><b>HunyuanVideo-1.5</b> — cinematic look.</li>
<li><b>ComfyUI</b> — if you already run Comfy at :8188.</li>
<li><b>Piper voices</b> — local narration. Lessac for explainers, Ryan for documentary.</li>
<li><b>Ollama Qwen2.5</b> — local scripts and titles. 7B on most PCs, 14B if you have RAM.</li>
</ul>
"""

MINI_SERIES = """
<h1>Mini Series</h1>
<p>Mini Series is a living episode pipeline. Each episode is 5–10 minutes and the picture path is <b>ViralForge Cinema</b> (native Wan/Cog). Maestro and text-card explainers are refused.</p>
<ol>
<li><b>Start series</b> with a title and topic.</li>
<li>Fill the virtual meeting: storyline, goals, tone, length, and notes.</li>
<li>Read the guardrails (clickbait, engagement bait, harassment, dangerous advice, rights, Cinema-only pictures, human review) and check each one.</li>
<li><b>Approve meeting</b>. Produce and Publish stay off until this gate opens. Editing the meeting after approval closes it again.</li>
<li><b>Produce Cinema package</b> writes a footage script and a project. It does not paint title cards.</li>
<li><b>Render with Cinema</b> runs only when <code>cinema_dry_run</code> is false. Dry-run cards are blocked.</li>
<li><b>Mark published</b> opens a 48-hour comment window. There is no background scheduler yet.</li>
<li>Paste comments (<code>Name: comment</code> or <code>Name | comment | likes</code>). Rank drops spam and toxicity, then <b>Draft next episode</b>. That draft is a new meeting and cannot render until you Approve it.</li>
</ol>
<p>YouTube OAuth is not required. If <code>youtube_api_key</code> or <code>youtube_credentials_path</code> is set in settings, the page says so, and live download stays unwired. Paste still works. Script drafts go through <code>ScriptEngineDrafter</code> (Ollama when it is running, otherwise the local template). A future Script Lab module can replace that drafter.</p>
"""

TROUBLESHOOT = """
<h1>Troubleshooting</h1>
<ul>
<li><b>Ollama pull failed</b> — install Ollama from ollama.com, keep it running, then Install models again.</li>
<li><b>Maestro weights failed</b> — Start Maestro with <code>start_maestro.bat</code> until http://127.0.0.1:42130 loads, then retry the Maestro rows.</li>
<li><b>Maestro not detected</b> — Run <code>start_maestro.bat</code> and wait until http://127.0.0.1:42130 responds. TrendForge auto-detects the Maestro folder under F:/pinokio/api/Maestro.git and the live API port. If it still misses, paste <code>http://127.0.0.1:42130</code> into Models &amp; Settings → Connection.</li>
<li><b>CUDA OOM</b> — switch to LTX distilled, Wan 5B, or Quick Explainer.</li>
<li><b>ffmpeg missing</b> — <code>winget install Gyan.FFmpeg</code> or keep <code>imageio-ffmpeg</code> installed.</li>
<li><b>No voice</b> — pick Piper after setup, or Windows SAPI (Settings → Time &amp; language → Speech).</li>
<li><b>Trends empty</b> — network/firewall. Search still works.</li>
<li><b>Stuck job</b> — Cancel, then Resume. Done shots are skipped.</li>
</ul>
<p>Use <b>Copy logs</b> on the Models page when asking for help. Nothing is uploaded automatically.</p>
"""


class HelpPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        title = QLabel("Help")
        title.setObjectName("title")
        tabs = QTabWidget()
        for name, html in (
            ("Getting Started", GETTING_STARTED),
            ("Formats", FORMAT_GUIDE),
            ("Mini Series", MINI_SERIES),
            ("Model Guide", MODEL_GUIDE),
            ("Troubleshooting", TROUBLESHOOT),
        ):
            browser = QTextBrowser()
            browser.setHtml(html)
            tabs.addTab(browser, name)
        root.addWidget(title)
        root.addWidget(tabs)
