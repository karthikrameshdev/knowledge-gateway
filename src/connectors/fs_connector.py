from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import hashlib
from .files import scan_files

from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import FilesystemConfig


class FilesystemConnector(BaseConnector):
    """Filesystem connector that searches documentation, specifications, and code files."""

    def __init__(self, config: FilesystemConfig):
        super().__init__(name="filesystem_scanner", source_type="filesystem", enabled=config.enabled)
        self.config = config

    def _resolve_dir(self, dir_path: str) -> Path:
        p = Path(dir_path)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / dir_path

    async def search(self, query, tags, top_k=None):
        return await self.run_blocking(self._search_sync, query, tags, top_k)

    async def health_check(self):
        return await self.run_blocking(self._health_sync)

    def _search_sync(
        self,
        query: str,
        tags: List[str],
        top_k: int = None,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled or not self.config.directories:
            return []

        q_clean = query.lower().strip()
        q_words = set(q_clean.split())
        if not q_words:
            return []

        matches = []
        limit = min(top_k or self.config.max_results, 20)

        for dir_cfg in self.config.directories:
            root_dir = self._resolve_dir(dir_cfg.path)
            if not root_dir.exists() or not root_dir.is_dir():
                continue

            for file_path in scan_files(root_dir, dir_cfg.patterns, self.config.max_files, self.config.max_file_bytes):

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                content_lower = content.lower()
                lines = content.splitlines()

                # Scoring
                exact_hits = content_lower.count(q_clean) if q_clean else 0
                word_hits = sum(1 for w in q_words if w in content_lower)

                if exact_hits == 0 and word_hits == 0:
                    continue

                score = min(1.0, 0.4 * (word_hits / float(len(q_words))) + 0.5 * (1.0 if exact_hits > 0 else 0.0))

                # Find best snippet around match
                matching_line_idx = 0
                for idx, line in enumerate(lines):
                    if any(w in line.lower() for w in q_words):
                        matching_line_idx = idx
                        break

                start_idx = max(0, matching_line_idx - 1)
                end_idx = min(len(lines), matching_line_idx + 4)
                snippet_lines = lines[start_idx:end_idx]
                snippet = "\n".join(snippet_lines)

                # Extract title
                title = file_path.stem.replace("_", " ").replace("-", " ").title()
                for line in lines[:5]:
                    if line.startswith("# "):
                        title = line.lstrip("# ").strip()
                        break

                matches.append((
                    score,
                    GatewayKnowledgeItem(
                        id=str(file_path.relative_to(root_dir.parent)),
                        source_type="filesystem",
                        title=title,
                        content=content,
                        snippet=snippet,
                        raw_score=round(score, 4),
                        provenance={
                            "connector": "filesystem_scanner",
                            "file_path": str(file_path),
                            "line_number": matching_line_idx + 1,
                            "file_size_bytes": file_path.stat().st_size,
                        },
                        metadata={
                            "extension": file_path.suffix,
                            "directory": str(dir_cfg.path),
                        },
                    )
                ))

        # Sort descending by raw score
        matches.sort(key=lambda x: (-x[0], x[1].id))
        return [m[1] for m in matches[:limit]]

    def _health_sync(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}

        monitored = []
        total_files = 0
        for dir_cfg in self.config.directories:
            p = self._resolve_dir(dir_cfg.path)
            count = sum(1 for _ in scan_files(p, dir_cfg.patterns, self.config.max_files, self.config.max_file_bytes))
            total_files += count
            monitored.append({"path": str(p), "exists": p.exists(), "files": count})

        return {
            "status": "healthy" if total_files else "degraded",
            "connector": self.name,
            "monitored_directories": monitored,
            "total_files": total_files,
        }
