# backend/app/connectors/markdown.py
"""
Markdown connector — walks a local directory tree and converts .md files
into Events. Authority scores are assigned by path pattern because a file's
location in the repo signals its trust level: a decision record in docs/adr/
is more authoritative than a random note under docs/.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..models.event import Event


def _authority_for_path(path: Path) -> tuple[str, float]:
    """Return (event_type_hint, authority_score) for a given file path."""
    parts = set(path.parts)
    name = path.name.lower()
    path_str = str(path).lower()

    if "decisions" in parts or "adr" in parts or "/decisions/" in path_str or "/adr/" in path_str:
        return ("adr", 0.95)
    if "runbooks" in parts or "playbooks" in parts or "/runbooks/" in path_str or "/playbooks/" in path_str:
        return ("runbook", 0.90)
    if name == "readme.md":
        return ("markdown_doc", 0.85)
    if name == "changelog.md":
        return ("markdown_doc", 0.80)
    if "api" in parts and ("docs" in parts or "doc" in parts):
        return ("markdown_doc", 0.80)
    if "docs" in parts or "doc" in parts or "wiki" in parts:
        return ("markdown_doc", 0.65)
    return ("markdown_doc", 0.60)


def _extract_title(content: str, fallback: str) -> str:
    """Pull the first H1 from the file, falling back to the filename."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


class MarkdownConnector:
    """
    Recursively ingests .md files from a local directory.

    Each file becomes one Event. The artifact_id is derived from the
    canonical file path so re-ingesting the same directory upserts rather
    than duplicates.
    """

    def __init__(self, allowed_groups: list[str] | None = None):
        self.allowed_groups = allowed_groups or ["engineering"]

    def get_events(self, directory: str) -> list[Event]:
        root = Path(directory).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {root}")

        events: list[Event] = []
        for md_file in sorted(root.rglob("*.md")):
            try:
                event = self._file_to_event(md_file, root)
                if event:
                    events.append(event)
            except Exception as e:
                print(f"[markdown] skipping {md_file}: {e}")

        print(f"[markdown] found {len(events)} .md files under {root}")
        return events

    def _file_to_event(self, path: Path, root: Path) -> Event | None:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            return None

        rel_path = path.relative_to(root)
        event_type_hint, authority = _authority_for_path(rel_path)
        title = _extract_title(content, path.stem.replace("-", " ").replace("_", " ").title())

        # Use file mtime as the event timestamp — closest proxy to "last changed".
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        # Stable artifact_id from the relative path so upserts work correctly.
        artifact_id = "md_" + re.sub(r"[^a-z0-9]+", "_", str(rel_path).lower()).strip("_")

        return Event(
            source="markdown",
            event_type=event_type_hint,
            actor="filesystem",
            timestamp_event=mtime,
            artifact_id=artifact_id,
            title=title,
            content=content,
            url=str(path),
            allowed_groups=self.allowed_groups,
            metadata={
                "authority_score": authority,
                "file_path": str(path),
                "rel_path": str(rel_path),
                "size_bytes": path.stat().st_size,
            },
        )
