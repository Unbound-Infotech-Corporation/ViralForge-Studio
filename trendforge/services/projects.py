from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trendforge.domain.models import Project, VideoScript
from trendforge.domain.serialize import dumps, project_from_dict
import json


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.root / project_id

    def save(self, project: Project) -> Path:
        folder = Path(project.folder) if project.folder else self.project_dir(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("clips", "audio", "captions", "output", "research"):
            (folder / name).mkdir(exist_ok=True)
        project.folder = str(folder)
        project.updated_at = datetime.now(timezone.utc).isoformat()
        path = folder / "project.json"
        path.write_text(dumps(project), encoding="utf-8")
        return path

    def load(self, project_id: str) -> Project:
        path = self.project_dir(project_id) / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        project = project_from_dict(data)
        project.folder = str(self.project_dir(project_id))
        return project

    def load_from_folder(self, folder: Path) -> Project:
        data = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        project = project_from_dict(data)
        project.folder = str(folder)
        return project

    def list_projects(self) -> list[Project]:
        entries: list[tuple[float, Path]] = []
        if not self.root.exists():
            return []
        for child in self.root.iterdir():
            if not (child / "project.json").exists():
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                mtime = 0.0
            entries.append((mtime, child))
        entries.sort(key=lambda pair: pair[0], reverse=True)
        items: list[Project] = []
        for _mtime, child in entries:
            try:
                items.append(self.load_from_folder(child))
            except Exception:
                continue
        return items

    def delete(self, project_id: str) -> None:
        import shutil

        folder = self.project_dir(project_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)

    def gallery_videos(self) -> list[Path]:
        videos: list[Path] = []
        for project in self.list_projects():
            if not project.folder:
                continue
            out = Path(project.folder) / "output"
            if not out.is_dir():
                continue
            videos.extend(sorted(out.glob("*.mp4")))
        return videos
