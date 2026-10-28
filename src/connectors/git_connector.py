import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import GitConfig

logger = logging.getLogger("GitConnector")


class GitConnector(BaseConnector):
    """Git repository connector inspecting commit histories, branches, and tracked files."""

    def __init__(self, config: GitConfig):
        super().__init__(name="git_repository", source_type="git", enabled=config.enabled)
        self.config = config

    def _resolve_repo(self, repo_path: str) -> Path:
        p = Path(repo_path)
        if p.is_absolute():
            return p
        return Path(__file__).resolve().parent.parent.parent / repo_path

    async def search(
        self,
        query: str,
        tags: List[str],
        top_k: int = 5,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled or not self.config.repositories:
            return []

        q_clean = query.lower().strip()
        q_words = set(q_clean.split())
        items = []

        for repo_cfg in self.config.repositories:
            repo_dir = self._resolve_repo(repo_cfg.path)
            if not repo_dir.exists() or not (repo_dir / ".git").exists():
                continue

            # 1. Search git commit logs
            try:
                cmd = [
                    "git", "log",
                    f"-n {repo_cfg.max_commits}",
                    "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s%x1f%b%x1e",
                    "--date=iso",
                ]
                res = subprocess.run(
                    " ".join(cmd),
                    shell=True,
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                )
                if res.returncode == 0 and res.stdout:
                    commits = res.stdout.strip().split("\x1e")
                    for c_raw in commits:
                        c_raw = c_raw.strip()
                        if not c_raw:
                            continue
                        parts = c_raw.split("\x1f")
                        if len(parts) >= 5:
                            commit_hash = parts[0].strip()
                            author_name = parts[1].strip()
                            author_email = parts[2].strip()
                            commit_date = parts[3].strip()
                            subject = parts[4].strip()
                            body = parts[5].strip() if len(parts) > 5 else ""

                            full_commit_text = f"{subject}\n{body}".lower()
                            hits = sum(1 for w in q_words if w in full_commit_text)
                            if hits > 0 or (q_clean and q_clean in full_commit_text):
                                score = min(0.95, 0.4 + 0.2 * hits)
                                items.append(GatewayKnowledgeItem(
                                    id=f"git_commit_{commit_hash[:8]}",
                                    source_type="git",
                                    title=f"Git Commit: {subject}",
                                    content=f"Commit: {commit_hash}\nAuthor: {author_name} <{author_email}>\nDate: {commit_date}\n\nSubject: {subject}\n\n{body}",
                                    snippet=f"[{commit_hash[:7]}] {subject} ({commit_date[:10]})",
                                    raw_score=round(score, 4),
                                    provenance={
                                        "connector": "git_repository",
                                        "repo": repo_cfg.name,
                                        "commit_hash": commit_hash,
                                        "author": f"{author_name} <{author_email}>",
                                        "commit_date": commit_date,
                                        "branch": repo_cfg.branch,
                                    },
                                    metadata={
                                        "type": "commit",
                                        "tags": ["git", "vcs", "commit"],
                                    },
                                ))
            except Exception as e:
                logger.debug("Git log search failed: %s", e)

            # 2. Search git tracked files
            try:
                res_files = subprocess.run(
                    ["git", "ls-files"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                )
                if res_files.returncode == 0:
                    for f in res_files.stdout.splitlines():
                        f_clean = f.lower()
                        if any(w in f_clean for w in q_words) and not f.startswith("."):
                            items.append(GatewayKnowledgeItem(
                                id=f"git_file_{f}",
                                source_type="git",
                                title=f"Tracked File: {f}",
                                content=f"Repository Tracked File: {f}\nRepo: {repo_cfg.name}\nBranch: {repo_cfg.branch}",
                                snippet=f"Tracked in git: {f}",
                                raw_score=0.75,
                                provenance={
                                    "connector": "git_repository",
                                    "repo": repo_cfg.name,
                                    "file_path": f,
                                    "branch": repo_cfg.branch,
                                },
                                metadata={
                                    "type": "tracked_file",
                                    "tags": ["git", "file"],
                                },
                            ))
            except Exception as e:
                logger.debug("Git file list failed: %s", e)

        items.sort(key=lambda x: x.raw_score, reverse=True)
        limit = min(top_k or 5, 20)
        return items[:limit]

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}

        repo_statuses = []
        for repo_cfg in self.config.repositories:
            repo_dir = self._resolve_repo(repo_cfg.path)
            if (repo_dir / ".git").exists():
                res = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                )
                head = res.stdout.strip() if res.returncode == 0 else "unknown"
                repo_statuses.append({
                    "name": repo_cfg.name,
                    "path": str(repo_dir),
                    "head": head,
                    "branch": repo_cfg.branch,
                })

        return {
            "status": "healthy" if repo_statuses else "degraded",
            "connector": self.name,
            "repositories": repo_statuses,
        }
