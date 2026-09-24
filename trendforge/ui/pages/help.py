from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QTextBrowser, QVBoxLayout, QWidget

GETTING_STARTED = """
<h1>Getting Started</h1>
<p>TrendForge Studio is a <b>local Windows app</b>. Core features never require a paid API.</p>
<ol>
<li>Finish the first-run wizard. It saves your channel voice and downloads the local models you leave checked (Piper narration, Whisper, Ollama scripts).</li>
<li>On <b>Create</b>, pick a <b>Format</b>, <b>Model</b>, and <b>Style</b>. Each row shows a logo and a label inside a thin frame.</li>
<li>Leave <b>Model</b> on Auto, or pick Wan 2.2 or <b>CogVideoX</b> (listed beside Wan). Quick Explainer works immediately on CPU.</li>
<li>Click <b>Generate</b>. The <b>Job Console</b> opens with the job (you can turn that off in the console). Watch Research → Script → Generate → Stitch → Finalize.</li>
<li>Open <b>Gallery</b> for <code>final.mp4</code> plus titles, pinned comment, community post, and description files.</li>
</ol>
<p><b>Channel</b> stores your name, niche, CTA, and brand voice so outros and YouTube sidecars stay consistent.</p>
<p><b>Job Console:</b> View → Job Console, the <b>Console</b> button on the status bar, or <b>Ctrl+`</b>.</p>
<p><b>Script Lab</b> (Produce) is an in-app browser for Grok, ChatGPT, Claude, and a research tab. Import a selection into the episode script Create uses. <b>Settings → Script AI</b> stores a bring-your-own API key for outlines, shot lists, dialogue, and virtual meeting notes. A chat-site subscription does not unlock the API. Local Ollama is the default provider and does not need a cloud key.</p>
<p><b>Mini Series</b> sits between Create and Channel. Approve the meeting, then Produce a Cinema package. Maestro and title-card renders are refused. Paste comments, rank them, and draft the next episode. The series is stored in <code>series.json</code>.</p>
<p><b>CogVideoX / Wan weights</b> go in the cinema models folder (default <code>F:\\TrendForge\\models\\cinema</code>): <code>cogvideox</code> next to <code>wan2.2-ti2v-5b</code> and <code>wan2.2-i2v</code>. Change the folder under Models → Connection. Missing weights are refused — Studio will not publish a title-card stand-in.</p>
<p>Quick Explainer is the intentional motion-graphics path. Cinematic models publish real footage only.</p>
"""

FORMAT_GUIDE = """
<h1>Formats that grow a channel</h1>
<ul>
<li><b>YouTube Short (9:16)</b> — 15–60s pattern interrupt. Post often.</li>
<li><b>Standard video (16:9)</b> — 3–8 min workhorse upload. Hook, context, takeaway, subscribe.</li>
<li><b>Long video</b> — 10–18 min session. Better for search and binge watch time.</li>
<li><b>Docuseries episode</b> — 18–40 min narrated investigation with cold open, evidence, cliffhanger.</li>
<li><b>Plan a season</b> — writes 4–6 episode briefs and a bible. Select a row, then Generate episode.</li>
</ul>
<p>Switch models anytime with the Model dropdown. Piper voices appear after setup installs them.</p>
"""

MODEL_GUIDE = """
<h1>Model Guide</h1>
<p>First-run setup and <b>Models &amp; Settings → Install models</b> download the free local stack (Piper, Whisper, Ollama). Cinematic checkpoints are files you place in the cinema models folder. TrendForge will not launch installers or UAC prompts.</p>
<ul>
<li><b>Auto</b> — ViralForge Cinema on this PC, or Quick Explainer when there is no suitable GPU.</li>
<li><b>ViralForge Cinema</b> — Wan 2.2 heroes, CogVideoX when you pick that row, then stitch. No card finals.</li>
<li><b>Quick Explainer</b> — motion-graphics cards. 0 GB VRAM. Use this on first install.</li>
<li><b>Wan 2.2 TI2V-5B</b> — lighter Wan. Prefer under 12 GB. Folder: <code>wan2.2-ti2v-5b</code>.</li>
<li><b>CogVideoX</b> — listed directly beside Wan. Folder: <code>cogvideox</code>.</li>
<li><b>Wan 2.2 A14B</b> — 16 GB+ recommended. Folder: <code>wan2.2-i2v</code>.</li>
<li><b>Clip + narrate</b> — paste a YouTube URL.</li>
<li><b>Piper voices</b> — local narration. Lessac for explainers, Ryan for documentary.</li>
<li><b>Ollama Qwen2.5</b> — local scripts and titles. 7B on most PCs, 14B if you have RAM. Default Script AI provider. Cloud providers use Settings → Script AI with your own key.</li>
</ul>
<p>Legacy engines stay out of the Create list.</p>
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
<p>YouTube OAuth is not required. If <code>youtube_api_key</code> or <code>youtube_credentials_path</code> is set in settings, the page says so, and live download stays unwired. Paste still works. Script drafts go through <code>ScriptEngineDrafter</code> (Ollama when it is running, otherwise the local template). <b>Script Lab</b> is already in the Produce nav; it can replace that drafter later through <code>ScriptDrafter</code>. The series file is <code>series.json</code>.</p>
"""

TROUBLESHOOT = """
<h1>Troubleshooting</h1>
<ul>
<li><b>Export refused / title cards</b> — cinematic models will not publish a card or silent final. Add weights under the cinema models folder, or pick Quick Explainer.</li>
<li><b>Headline-only cinema prompt</b> — each shot is locked to its beat and voiceover (must depict / must not depict). A headline with no beat or VO is refused instead of generic B-roll.</li>
<li><b>CogVideoX or Wan missing</b> — copy the checkpoint into <code>cinema/cogvideox</code> or <code>cinema/wan2.2-ti2v-5b</code>. The path is on Models → Connection.</li>
<li><b>Ollama pull failed</b> — install Ollama from ollama.com, keep it running, then Install models again. The local Script AI provider does not use a cloud key.</li>
<li><b>CUDA OOM</b> — switch to Wan 5B, CogVideoX if it fits, or Quick Explainer.</li>
<li><b>ffmpeg missing</b> — <code>winget install Gyan.FFmpeg</code> or keep <code>imageio-ffmpeg</code> installed.</li>
<li><b>No voice</b> — pick Piper after setup, or Windows SAPI (Settings → Time &amp; language → Speech).</li>
<li><b>Where is the log?</b> — View → Job Console, status-bar <b>Console</b>, or <b>Ctrl+`</b>. Help → Copy logs copies the file log. Nothing is uploaded.</li>
<li><b>Trends empty</b> — network/firewall. Search still works.</li>
<li><b>Script Lab browser missing</b> — install Qt WebEngine and restart: <code>pip install PySide6-Addons</code>. Paste-import and Script AI still work without it.</li>
<li><b>Script AI failed</b> — chat logins are not API keys. Set provider, key, and model under Settings → Script AI. Ollama must be running for the local provider.</li>
<li><b>Stuck job</b> — Cancel, then Resume. Done shots are skipped.</li>
</ul>
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
