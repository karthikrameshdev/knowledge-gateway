import re
import time
import threading
from .files import scan_files
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import yaml

from .base import BaseConnector
from ..models import GatewayKnowledgeItem
from ..config import OKFConfig

FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class OKFDocument:
    def __init__(
        self,
        file_path: Path,
        doc_id: str,
        doc_type: str,
        title: str,
        version: str,
        status: str,
        updated_at: str,
        verified_by: Optional[str],
        tags: List[str],
        relations: Dict[str, Any],
        body_markdown: str,
        full_content: str,
    ):
        self.file_path = file_path
        self.doc_id = doc_id
        self.doc_type = doc_type
        self.title = title
        self.version = version
        self.status = status
        self.updated_at = updated_at
        self.verified_by = verified_by
        self.tags = tags
        self.relations = relations
        self.body_markdown = body_markdown
        self.full_content = full_content


class OKFConnector(BaseConnector):
    """Open Knowledge Format connector with deterministic graph traversal and YAML frontmatter indexing."""

    def __init__(self, config: OKFConfig):
        super().__init__(name="okf_knowledge_point", source_type="okf", enabled=config.enabled)
        self.config = config
        self.root_dir = Path(config.root_dir)
        self.documents: Dict[str, OKFDocument] = {}
        self.dependents_index: Dict[str, Set[str]] = {}  # target -> set of docs depending on it
        self.governed_index: Dict[str, Set[str]] = {}    # policy -> set of docs governed by it
        self._index_lock = threading.RLock()
        self._loaded_at = 0.0

    def _load_documents(self):
        self.documents.clear()
        self.dependents_index.clear()
        self.governed_index.clear()

        if not self.root_dir.is_absolute():
            root = Path(__file__).resolve().parent.parent.parent / self.config.root_dir
        else:
            root = self.root_dir

        if not root.exists() or not root.is_dir():
            return

        for p in scan_files(root, ["*.md"], self.config.max_files, self.config.max_file_bytes):
            try:
                content = p.read_text(encoding="utf-8")
                match = FRONTMATTER_REGEX.match(content)
                if not match:
                    # Plain markdown fallback
                    doc_id = p.stem
                    doc = OKFDocument(
                        file_path=p,
                        doc_id=doc_id,
                        doc_type="unclassified",
                        title=doc_id.replace("-", " ").title(),
                        version="1.0.0",
                        status="active",
                        updated_at="",
                        verified_by=None,
                        tags=[],
                        relations={},
                        body_markdown=content.strip(),
                        full_content=content,
                    )
                else:
                    fm_raw = match.group(1)
                    body = match.group(2).strip()
                    meta = yaml.safe_load(fm_raw) or {}
                    if not isinstance(meta, dict):
                        continue
                    doc_id = str(meta.get("id") or p.stem)
                    tags = meta.get("tags") or []
                    if isinstance(tags, str):
                        tags = [tags]
                    tags = [str(t) for t in tags if isinstance(t, (str, int))]
                    relations = meta.get("relations") or {}
                    if not isinstance(relations, dict):
                        relations = {}
                    relations = {str(k): ([str(v)] if isinstance(v, str) else [str(x) for x in v] if isinstance(v, list) else []) for k, v in relations.items()}

                    doc = OKFDocument(
                        file_path=p,
                        doc_id=doc_id,
                        doc_type=str(meta.get("type", "document")),
                        title=str(meta.get("title") or doc_id.replace("-", " ").title()),
                        version=str(meta.get("version", "1.0.0")),
                        status=str(meta.get("status", "active")),
                        updated_at=str(meta.get("updated_at", "")),
                        verified_by=meta.get("verified_by"),
                        tags=tags,
                        relations=relations,
                        body_markdown=body,
                        full_content=content,
                    )

                self.documents[doc.doc_id] = doc

                # Index reverse relations
                deps = doc.relations.get("depends_on", [])
                if isinstance(deps, str):
                    deps = [deps]
                for d in deps:
                    self.dependents_index.setdefault(d, set()).add(doc.doc_id)

                gov = doc.relations.get("governed_by", [])
                if isinstance(gov, str):
                    gov = [gov]
                for g in gov:
                    self.governed_index.setdefault(g, set()).add(doc.doc_id)

            except Exception:
                pass

    async def search(self, query, tags, top_k=None):
        return await self.run_blocking(self._locked_search, query, tags, top_k)

    async def health_check(self):
        return await self.run_blocking(self._health_sync)

    def _locked_search(self, query, tags, top_k):
        with self._index_lock:
            if time.monotonic() - self._loaded_at >= self.config.refresh_interval_seconds:
                self._load_documents()
                self._loaded_at = time.monotonic()
            return self._search_sync(query, tags, top_k)

    def _search_sync(
        self,
        query: str,
        tags: List[str],
        top_k: int = None,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled:
            return []

        # Refresh index if documents empty
        if not self.documents:
            self._load_documents()

        q_lower = query.lower()
        matched_docs: List[Tuple[OKFDocument, List[str]]] = []  # (doc, traversal_path)

        # Resolve any named entity, then follow its explicit relations. No fixture-specific names.
        seeds = [doc for doc in self.documents.values() if doc.doc_id.lower() in q_lower or doc.title.lower() in q_lower]
        if not seeds:
            seeds = [doc for doc in self.documents.values() if any(str(tag).lower() in q_lower for tag in doc.tags)]
        visited = set()
        for doc in sorted(seeds, key=lambda d: d.doc_id):
            if doc.doc_id in visited:
                continue
            visited.add(doc.doc_id)
            matched_docs.append((doc, [f"Entity: {doc.doc_id}"]))
            related = set()
            if any(word in q_lower for word in ['depend', 'uses', 'service']):
                related.update(self.dependents_index.get(doc.doc_id, set()))
            if any(word in q_lower for word in ['govern', 'comply', 'policy', 'standard']):
                related.update(self.governed_index.get(doc.doc_id, set()))
            for relation in ['depends_on', 'governed_by', 'applies_to']:
                related.update(doc.relations.get(relation, []))
            if self.config.deterministic_traversal:
                for related_id in sorted(related):
                    if related_id in self.documents and related_id not in visited:
                        visited.add(related_id)
                        matched_docs.append((self.documents[related_id], [doc.doc_id, f"explicit relation -> {related_id}"]))

        # 2. Entity ID and Tag matching
        q_words = set(q_lower.split())
        query_tags = [t.lower() for t in tags]

        for doc_id, doc in sorted(self.documents.items()):
            if any(doc_id == m[0].doc_id for m in matched_docs):
                continue

            # Direct doc_id match or title match
            score_factor = 0
            if doc_id in q_lower or doc.title.lower() in q_lower:
                score_factor += 2

            # Tag match
            doc_tags = [t.lower() for t in doc.tags]
            tag_hits = set(doc_tags) & (set(query_tags) | q_words)
            if tag_hits:
                score_factor += len(tag_hits)

            # Keyword match in body
            body_hits = sum(1 for w in q_words if len(w) > 2 and w in doc.body_markdown.lower())
            if body_hits > 1:
                score_factor += 1

            if score_factor > 0:
                matched_docs.append((doc, [f"Metadata / Tag match (hits: {score_factor})"]))

        # Format items
        items: List[GatewayKnowledgeItem] = []
        limit = min(top_k or self.config.top_k, 20)

        for doc, path in matched_docs[:limit]:
            snippet = doc.body_markdown[:220] + ("..." if len(doc.body_markdown) > 220 else "")
            item = GatewayKnowledgeItem(
                id=doc.doc_id,
                source_type="okf",
                title=doc.title,
                content=f"# {doc.title} ({doc.version})\nStatus: {doc.status}\n\n{doc.body_markdown}",
                snippet=snippet,
                raw_score=0.90 if len(path) > 1 else 0.82,
                provenance={
                    "connector": "okf_knowledge_point",
                    "file_path": str(doc.file_path),
                    "version": doc.version,
                    "status": doc.status,
                    "verified_by": doc.verified_by,
                    "updated_at": doc.updated_at,
                    "traversal_path": path,
                },
                metadata={
                    "doc_type": doc.doc_type,
                    "tags": doc.tags,
                    "relations": doc.relations,
                },
            )
            items.append(item)

        return items

    def _health_sync(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}
        with self._index_lock:
            self._load_documents()
            self._loaded_at = time.monotonic()
        return {
            "status": "healthy" if self.documents else "degraded",
            "connector": self.name,
            "root_dir": str(self.root_dir),
            "documents_count": len(self.documents),
            "dependents_indexed": len(self.dependents_index),
            "policies_indexed": len(self.governed_index),
        }
