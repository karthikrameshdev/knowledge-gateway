import hashlib
import math
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from .models import GatewayKnowledgeItem, ActivityCandidateTrace
from .config import ONNXEngineConfig

logger = logging.getLogger("ONNXEngine")


class ONNXConsolidatorEngine:
    """Evaluates, scores, and consolidates multi-source candidates using a local ONNX model."""

    def __init__(self, config: Optional[ONNXEngineConfig] = None):
        self.config = config or ONNXEngineConfig()
        self.session = None
        self.is_onnx_active = False
        self._init_session()

    def _init_session(self):
        if not self.config.enabled:
            logger.info("ONNX engine disabled in configuration.")
            return

        model_path = Path(self.config.model_path)
        if not model_path.is_absolute():
            # Try relative to repo root
            root_dir = Path(__file__).resolve().parent.parent
            model_path = root_dir / self.config.model_path

        if not model_path.exists():
            logger.warning("ONNX model file not found at %s. Using heuristic reranker fallback.", model_path)
            return

        try:
            import onnxruntime as ort
            # Configure lightweight session
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(str(model_path), sess_options=opts)
            self.is_onnx_active = True
            logger.info("Loaded ONNX model successfully from %s", model_path)
        except Exception as e:
            logger.warning("Failed to initialize ONNX Runtime session: %s. Using fallback.", e)
            self.session = None
            self.is_onnx_active = False

    def _pseudo_vector(self, text: str, dim: int = 128) -> np.ndarray:
        """Generates fast deterministic L2-normalized vector for semantic approximation."""
        vec = np.zeros(dim, dtype=np.float32)
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec

        for w in words:
            h = int(hashlib.sha256(w.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            weight = math.log(1.0 + len(w))
            vec[idx] += sign * weight

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec /= norm
        return vec

    def _extract_features(
        self,
        query: str,
        tags: List[str],
        item: GatewayKnowledgeItem,
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """Extracts 8-dimensional feature vector for a candidate item."""
        q_clean = query.lower().strip()
        q_words = set(q_clean.split())
        title_lower = item.title.lower()
        content_lower = item.content.lower()
        combined_text = f"{title_lower} {content_lower}"

        # 0: Semantic similarity
        # If item has a raw similarity score from RAG, blend it
        q_vec = self._pseudo_vector(q_clean)
        doc_vec = self._pseudo_vector(combined_text[:1000])
        approx_sim = float(np.dot(q_vec, doc_vec))
        semantic_sim = max(0.0, min(1.0, (approx_sim + 1.0) / 2.0))
        if item.source_type == "rag" and item.raw_score > 0:
            semantic_sim = 0.5 * semantic_sim + 0.5 * min(1.0, item.raw_score)

        # 1: Lexical overlap (Jaccard on words)
        doc_words = set(combined_text.split())
        if q_words and doc_words:
            lexical_overlap = len(q_words & doc_words) / float(len(q_words | doc_words))
        else:
            lexical_overlap = 0.0
        lexical_overlap = min(1.0, lexical_overlap * 2.5)  # Scale up for sparse text

        # 2: Title match
        if q_words:
            title_hits = sum(1 for w in q_words if w in title_lower)
            title_match = title_hits / float(len(q_words))
        else:
            title_match = 0.0

        # 3: Tag match
        item_tags = [t.lower() for t in item.metadata.get("tags", [])]
        if isinstance(item_tags, str):
            item_tags = [item_tags]
        query_tags = [t.lower() for t in tags]
        all_query_tags = set(query_tags) | q_words
        if item_tags and all_query_tags:
            tag_hits = sum(1 for t in item_tags if any(qt in t or t in qt for qt in all_query_tags))
            tag_match = min(1.0, tag_hits / float(len(item_tags)))
        else:
            tag_match = 0.2 if not tags else 0.0

        # 4: Recency score (default 0.85)
        recency_score = 0.85

        # 5: Source confidence prior
        confidence_map = {
            "okf": 0.95,
            "sql": 0.90,
            "git": 0.85,
            "filesystem": 0.85,
            "rag": 0.80,
        }
        source_confidence = confidence_map.get(item.source_type, 0.75)

        # 6: Content length prior (healthy informative length)
        content_len = len(item.content)
        if content_len < 20:
            length_prior = 0.2
        elif content_len < 100:
            length_prior = 0.6
        else:
            length_prior = 0.95

        # 7: Exact phrase match
        exact_match = 1.0 if q_clean and q_clean in combined_text else 0.0

        feature_dict = {
            "semantic_sim": round(semantic_sim, 4),
            "lexical_overlap": round(lexical_overlap, 4),
            "title_match": round(title_match, 4),
            "tag_match": round(tag_match, 4),
            "recency_score": round(recency_score, 4),
            "source_confidence": round(source_confidence, 4),
            "length_prior": round(length_prior, 4),
            "exact_match": round(exact_match, 4),
        }

        feature_vec = np.array([
            semantic_sim,
            lexical_overlap,
            title_match,
            tag_match,
            recency_score,
            source_confidence,
            length_prior,
            exact_match,
        ], dtype=np.float32)

        return feature_vec, feature_dict

    def consolidate_and_rerank(
        self,
        query: str,
        tags: List[str],
        candidates: List[GatewayKnowledgeItem],
        min_score: Optional[float] = None,
    ) -> Tuple[List[GatewayKnowledgeItem], List[ActivityCandidateTrace]]:
        """Scores all candidate items through ONNX model, deduplicates, and filters by min_score."""
        if not candidates:
            return [], []

        threshold = min_score if min_score is not None else self.config.score_threshold

        # Deduplicate candidates across sources by canonical key
        seen_keys = set()
        unique_candidates: List[GatewayKnowledgeItem] = []
        for c in candidates:
            # Canonical key combines source and id or clean title
            canonical_key = f"{c.source_type}:{c.id.strip().lower()}"
            if canonical_key not in seen_keys:
                seen_keys.add(canonical_key)
                unique_candidates.append(c)

        # Build feature matrix
        feature_rows = []
        feature_dicts = []
        for c in unique_candidates:
            f_vec, f_dict = self._extract_features(query, tags, c)
            feature_rows.append(f_vec)
            feature_dicts.append(f_dict)

        feature_matrix = np.stack(feature_rows, axis=0)

        # Run ONNX inference if active
        if self.is_onnx_active and self.session is not None:
            try:
                outputs = self.session.run(["score"], {"features": feature_matrix})
                scores = outputs[0].flatten().tolist()
            except Exception as e:
                logger.error("ONNX inference failed: %s. Falling back to heuristic scoring.", e)
                scores = self._heuristic_scores(feature_rows)
        else:
            scores = self._heuristic_scores(feature_rows)

        # Attach scores & build traces
        traces: List[ActivityCandidateTrace] = []
        scored_items: List[GatewayKnowledgeItem] = []

        for item, score, f_dict in zip(unique_candidates, scores, feature_dicts):
            final_score = round(float(score), 4)
            item.onnx_score = final_score
            item.score = final_score
            accepted = final_score >= threshold

            traces.append(ActivityCandidateTrace(
                id=item.id,
                source_type=item.source_type,
                title=item.title,
                raw_score=round(item.raw_score, 4),
                onnx_score=final_score,
                features=f_dict,
                accepted=accepted,
            ))

            if accepted:
                scored_items.append(item)

        # Sort descending by ONNX score
        scored_items.sort(key=lambda x: x.score, reverse=True)
        traces.sort(key=lambda x: x.onnx_score, reverse=True)

        return scored_items, traces

    def _heuristic_scores(self, feature_rows: List[np.ndarray]) -> List[float]:
        """Heuristic scoring when ONNX engine is disabled or fallback is active."""
        weights = np.array([0.30, 0.20, 0.20, 0.10, 0.05, 0.10, 0.05, 0.20], dtype=np.float32)
        scores = []
        for f in feature_rows:
            raw_dot = float(np.dot(f, weights))
            # Sigmoid shaping
            score = 1.0 / (1.0 + math.exp(-3.0 * (raw_dot - 0.5)))
            scores.append(score)
        return scores
