"""Small offline retrieval evaluation utility.

Run from the project root with a JSONL dataset containing question and
expected_source fields. It reports Recall@K, Precision@K, MRR, and latency.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.rag.retriever import get_retriever


def evaluate(dataset_path: Path, top_k: int = 5) -> dict[str, float]:
    rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retriever = get_retriever(top_k=top_k)
    hits = 0
    retrieved_relevant = 0
    reciprocal_rank = 0.0
    latencies = []
    for row in rows:
        started = time.perf_counter()
        documents = retriever.retrieve(row["question"])
        latencies.append((time.perf_counter() - started) * 1000)
        filenames = [doc.metadata.get("source_filename") for doc in documents]
        expected = row.get("expected_source")
        relevant = sum(filename == expected for filename in filenames)
        retrieved_relevant += relevant
        if relevant:
            hits += 1
            reciprocal_rank += 1 / (filenames.index(expected) + 1)
    count = len(rows) or 1
    denominator = max(len(rows) * top_k, 1)
    return {
        "recall_at_k": hits / count,
        "precision_at_k": retrieved_relevant / denominator,
        "mrr": reciprocal_rank / count,
        "average_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
    }


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "evaluation/dataset.jsonl")
    print(json.dumps(evaluate(path), indent=2))
