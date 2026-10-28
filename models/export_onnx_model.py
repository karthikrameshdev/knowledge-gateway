#!/usr/bin/env python3
"""Exports a compact, high-performance ONNX neural re-ranking & consolidation model

for the Knowledge Gateway.
"""
from pathlib import Path
import numpy as np
import onnx
from onnx import helper, TensorProto
import onnxruntime as ort

MODELS_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODELS_DIR / "reranker.onnx"


def build_and_export_onnx_model(output_path: Path = MODEL_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Input: features matrix [N, 8]
    # 0: semantic_similarity (0..1)
    # 1: lexical_overlap (0..1)
    # 2: title_match (0..1)
    # 3: tag_match (0..1)
    # 4: recency_score (0..1)
    # 5: source_confidence (0..1)
    # 6: content_length_prior (0..1)
    # 7: exact_phrase_match (0..1)
    X = helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, 8])
    Y = helper.make_tensor_value_info("score", TensorProto.FLOAT, [None, 1])

    # Weights:
    # W1: [8, 16] with specific feature sensitivities
    W1 = np.array([
        [0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.70, 0.75, 0.80, 0.70, 0.65, 0.75, 0.80, 0.70, 0.65, 0.75],  # semantic
        [0.45, 0.40, 0.50, 0.45, 0.40, 0.35, 0.45, 0.40, 0.45, 0.40, 0.35, 0.40, 0.45, 0.40, 0.35, 0.40],  # lexical
        [0.60, 0.65, 0.60, 0.55, 0.50, 0.55, 0.60, 0.55, 0.60, 0.55, 0.50, 0.55, 0.60, 0.55, 0.50, 0.55],  # title
        [0.50, 0.45, 0.50, 0.45, 0.40, 0.45, 0.50, 0.45, 0.50, 0.45, 0.40, 0.45, 0.50, 0.45, 0.40, 0.45],  # tag
        [0.25, 0.20, 0.25, 0.20, 0.20, 0.20, 0.25, 0.20, 0.25, 0.20, 0.20, 0.20, 0.25, 0.20, 0.20, 0.20],  # recency
        [0.35, 0.30, 0.35, 0.30, 0.30, 0.30, 0.35, 0.30, 0.35, 0.30, 0.30, 0.30, 0.35, 0.30, 0.30, 0.30],  # confidence
        [0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15],  # length
        [0.70, 0.75, 0.70, 0.65, 0.60, 0.65, 0.70, 0.65, 0.70, 0.65, 0.60, 0.65, 0.70, 0.65, 0.60, 0.65],  # exact
    ], dtype=np.float32)
    B1 = np.full((16,), -0.15, dtype=np.float32)

    # W2: [16, 8]
    W2 = np.full((16, 8), 0.15, dtype=np.float32)
    B2 = np.full((8,), -0.10, dtype=np.float32)

    # W3: [8, 1]
    W3 = np.full((8, 1), 0.35, dtype=np.float32)
    B3 = np.array([-2.20], dtype=np.float32)

    node_g1 = helper.make_node("Gemm", ["features", "W1", "B1"], ["h1"], alpha=1.0, beta=1.0)
    node_r1 = helper.make_node("Relu", ["h1"], ["a1"])
    node_g2 = helper.make_node("Gemm", ["a1", "W2", "B2"], ["h2"], alpha=1.0, beta=1.0)
    node_r2 = helper.make_node("Relu", ["h2"], ["a2"])
    node_g3 = helper.make_node("Gemm", ["a2", "W3", "B3"], ["logits"], alpha=1.0, beta=1.0)
    node_sig = helper.make_node("Sigmoid", ["logits"], ["score"])

    w1_t = helper.make_tensor("W1", TensorProto.FLOAT, [8, 16], W1.flatten().tolist())
    b1_t = helper.make_tensor("B1", TensorProto.FLOAT, [16], B1.flatten().tolist())
    w2_t = helper.make_tensor("W2", TensorProto.FLOAT, [16, 8], W2.flatten().tolist())
    b2_t = helper.make_tensor("B2", TensorProto.FLOAT, [8], B2.flatten().tolist())
    w3_t = helper.make_tensor("W3", TensorProto.FLOAT, [8, 1], W3.flatten().tolist())
    b3_t = helper.make_tensor("B3", TensorProto.FLOAT, [1], B3.flatten().tolist())

    graph = helper.make_graph(
        [node_g1, node_r1, node_g2, node_r2, node_g3, node_sig],
        "KnowledgeGatewayReranker",
        [X],
        [Y],
        [w1_t, b1_t, w2_t, b2_t, w3_t, b3_t],
    )
    opset = helper.make_opsetid("", 17)
    model = helper.make_model(
        graph,
        producer_name="knowledge-gateway-engine",
        opset_imports=[opset],
        ir_version=10,
    )
    onnx.checker.check_model(model)
    onnx.save(model, str(output_path))
    print(f"Exported ONNX model successfully to: {output_path}")

    # Validate with inference session
    sess = ort.InferenceSession(str(output_path))
    test_input = np.array([
        [0.85, 0.60, 1.0, 1.0, 0.9, 0.95, 0.7, 1.0],  # High relevance candidate
        [0.10, 0.05, 0.0, 0.0, 0.2, 0.50, 0.1, 0.0],  # Low relevance noise candidate
    ], dtype=np.float32)
    scores = sess.run(["score"], {"features": test_input})[0]
    print(f"Validation test outputs -> High: {scores[0][0]:.4f}, Low: {scores[1][0]:.4f}")
    assert scores[0][0] > scores[1][0], "Scoring order assertion failed"
    return output_path


if __name__ == "__main__":
    build_and_export_onnx_model()
