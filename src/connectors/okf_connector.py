import re
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
        if self.enabled:
            self._load_documents()

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

        for p in root.rglob("*.md"):
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
                    doc_id = str(meta.get("id") or p.stem)
                    tags = meta.get("tags") or []
                    if isinstance(tags, str):
                        tags = [tags]
                    relations = meta.get("relations") or {}

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

    async def search(
        self,
        query: str,
        tags: List[str],
        top_k: int = 5,
    ) -> List[GatewayKnowledgeItem]:
        if not self.enabled:
            return []

        # Refresh index if documents empty
        if not self.documents:
            self._load_documents()

        q_lower = query.lower()
        matched_docs: List[Tuple[OKFDocument, List[str]]] = []  # (doc, traversal_path)

        # 1. Deterministic Graph Traversal for Relational Queries
        if "vault" in q_lower and ("depend" in q_lower or "service" in q_lower or "uses" in q_lower):
            root_doc = self.documents.get("vault-secrets-engine")
            if root_doc:
                matched_docs.append((root_doc, ["Entity: vault-secrets-engine"]))
            dependents = self.dependents_index.get("vault-secrets-engine", set())
            for dep_id in dependents:
                dep_doc = self.documents.get(dep_id)
                if dep_doc and dep_doc not in [d[0] for d in matched_docs]:
                    matched_docs.append((dep_doc, ["vault-secrets-engine", f"reverse depends_on -> {dep_id}"]))

        if "pci" in q_lower and ("govern" in q_lower or "comply" in q_lower or "standard" in q_lower):
            policy_doc = self.documents.get("pci-dss-compliance")
            if policy_doc:
                matched_docs.append((policy_doc, ["Policy: pci-dss-compliance"]))
                applies = policy_doc.relations.get("applies_to", [])
                for app_id in applies:
                    app_doc = self.documents.get(app_id)
                    if app_doc and app_doc not in [d[0] for d in matched_docs]:
                        matched_docs.append((app_doc, ["pci-dss-compliance", f"applies_to -> {app_id}"]))

        if "zero trust" in q_lower or "zero-trust" in q_lower:
            zt_doc = self.documents.get("zero-trust-network")
            if zt_doc:
                matched_docs.append((zt_doc, ["Policy: zero-trust-network"]))
                applies = zt_doc.relations.get("applies_to", [])
                for app_id in applies:
                    app_doc = self.documents.get(app_id)
                    if app_doc and app_doc not in [d[0] for d in matched_docs]:
                        matched_docs.append((app_doc, ["zero-trust-network", f"applies_to -> {app_id}"]))

        if "disaster" in q_lower or "failover" in q_lower or "rto" in q_lower:
            dr_doc = self.documents.get("disaster-recovery")
            if dr_doc and dr_doc not in [d[0] for d in matched_docs]:
                matched_docs.append((dr_doc, ["Runbook: disaster-recovery"]))

        # 2. Entity ID and Tag matching
        q_words = set(q_lower.split())
        query_tags = [t.lower() for t in tags]

        for doc_id, doc in self.documents.items():
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
            body_hits = sum(1 for w in q_words if w in doc.body_markdown.lower())
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

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "connector": self.name}
        return {
            "status": "healthy",
            "connector": self.name,
            "root_dir": str(self.root_dir),
            "documents_count": len(self.documents),
            "dependents_indexed": len(self.dependents_index),
            "policies_indexed": len(self.governed_index),
        }
