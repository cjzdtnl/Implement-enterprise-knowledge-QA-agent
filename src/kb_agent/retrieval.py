from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from rank_bm25 import BM25Okapi

from .schema import Corpus

# General short phrase normalization, shared by document and query processing.
# Development examples and held-out queries are recorded in data/retrieval_queries.json.
SYNONYMS = {
    "报账": "报销", "报帐": "报销", "报消": "报销",
    "单据": "材料", "凭据": "材料", "递交": "提交", "上交": "提交",
    "口令": "密码", "订会议室": "会议室预约", "订房间": "会议室预约",
}


def tokenize(text: str, normalize: bool = True) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    if normalize:
        for source, target in SYNONYMS.items():
            text = text.replace(source, target)
    tokens = []
    # Chinese bigrams retain phrase specificity; no standalone ubiquitous Han chars.
    for chunk in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text):
        if re.fullmatch(r"[\u4e00-\u9fff]+", chunk) and len(chunk) > 1:
            tokens.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
        else:
            tokens.append(chunk)
    return tokens


class KnowledgeBase:
    def __init__(self, path: Path, normalize: bool = True):
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.corpus = Corpus.model_validate(json.loads(raw.decode("utf-8-sig")))
        self.normalize = normalize
        self.sections = {}
        self.rows = []
        for doc in self.corpus.documents:
            for section in doc.sections:
                row = {
                    "doc_id": doc.doc_id, "section_id": section.section_id,
                    "title": doc.title, "version_date": doc.version_date,
                    "text": section.text, "synthetic": True,
                    "scope": doc.scope, "supersedes": doc.supersedes, "priority": doc.priority,
                }
                self.sections[(doc.doc_id, section.section_id)] = row
                self.rows.append(row)
        self.tokens = [tokenize(r["title"] + " " + r["text"], normalize) for r in self.rows]
        if not any(self.tokens):
            raise ValueError("corpus has no indexable content")
        self.index = BM25Okapi(self.tokens)

    def search(self, query: str, top_k: int) -> list[dict]:
        tokens = tokenize(query, self.normalize)
        if not tokens:
            return []
        scores = self.index.get_scores(tokens)
        # Scores may be zero/negative in a small corpus (BM25 IDF behavior).
        # Use actual shared tokens to gate candidates; scores only rank them.
        # Never pad top-k with rows that have no matching token.
        ranked = sorted(range(len(self.rows)), key=lambda i: (-float(scores[i]), i))
        hits = []
        for i in ranked:
            if not set(tokens).intersection(self.tokens[i]):
                continue
            row = self.rows[i]
            hits.append({k: row[k] for k in ("doc_id", "section_id", "title", "version_date")} | {
                "score": round(float(scores[i]), 6), "preview": row["text"][:100],
            })
            if len(hits) == top_k:
                break
        return hits
