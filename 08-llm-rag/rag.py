"""A small retrieval-augmented (RAG) assistant over Ethiopian public health guidelines.

    python rag.py "What is the community case definition of suspected cholera?"
    python rag.py "..." --model qwen/qwen3.5-9b --k 8
    python rag.py "..." --retriever embed

How it works, in three steps:
  1. **Index** (once): read the guideline PDFs, cut each page into overlapping passages of
     about 200 words, and build a keyword index (TF-IDF) over them.
  2. **Retrieve**: for a question, find the k passages that share the most (rare) words with it, or, with
     `--retriever embed`, the k passages closest in meaning (a small embedding model).
  3. **Generate**: send the question plus those passages to an LLM, with instructions to answer
     only from them, cite them as [1], [2] ..., and say so when the answer isn't there.

Every part is a setting you can change (chunk size, k, model, prompt) and every change can make
answers better or worse: that is what evaluate.py measures.

The LLM is called through an OpenAI-compatible API. In the workshop that is OpenRouter (hosted
open-weight models, one shared key); a self-hosted server (vLLM, Ollama) works the same way:
set LLM_BASE_URL to its address.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DOCS = REPO / "downloads" / "guidelines"          # filled by: python scripts/download.py guidelines
INDEX_CACHE = HERE / "index"                      # passages, cached after the first run

OPENROUTER = "https://openrouter.ai/api/v1"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"            # 67 MB, English; runs on onnxruntime via fastembed (no PyTorch)
REFUSAL = "The guidelines provided do not cover this."

logging.getLogger("pypdf").setLevel(logging.ERROR)   # some PDFs trigger harmless parser warnings


@dataclass
class Settings:
    """Everything that defines one version of the assistant. Logged with every evaluation run."""
    model: str = "google/gemma-4-26b-a4b-it"      # open-weight (Apache-2.0), hosted on OpenRouter
    retriever: str = "tfidf"                       # "tfidf" (shared words) or "embed" (meaning, EMBED_MODEL)
    k: int = 5                                     # passages given to the model
    chunk_words: int = 200                         # passage length
    overlap_words: int = 40                        # overlap between consecutive passages
    prompt_version: str = "v1"
    temperature: float = 0.0                       # as repeatable as the provider allows
    thinking: bool = False                         # "reasoning" models think before answering: slower, costlier


PROMPTS = {
    "v1": (
        "You answer questions from health workers in Ethiopia using ONLY the numbered guideline "
        "passages provided.\n"
        "- Base every statement on the passages and cite them like [1] or [2][3].\n"
        "- If the passages do not contain the answer, reply exactly: \"" + REFUSAL + "\"\n"
        "- Be concise: at most 4 sentences. Quote numbers, doses and cut-offs exactly.\n"
        "- Answer in the language of the question."
    ),
}


# ---------------------------------------------------------------- 1. index


def document_titles():
    """File stem -> human-readable title, from the download manifest."""
    manifest = json.loads((REPO / "scripts" / "downloads.json").read_text())
    return {Path(i["file"]).stem: i["description"] for i in manifest["guidelines"]}


def load_pages(folder=DOCS):
    """One row per PDF page: doc (file stem), page (1-based), text."""
    from pypdf import PdfReader

    files = sorted(Path(folder).glob("*.pdf"))
    if not files:
        raise FileNotFoundError(f"no PDFs in {folder}: run `python scripts/download.py guidelines` from the repo root")
    rows = []
    for f in files:
        for i, page in enumerate(PdfReader(f).pages, 1):
            text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
            if len(text.split()) >= 20:          # skip blank and image-only pages
                rows.append({"doc": f.stem, "page": i, "text": text})
    return pd.DataFrame(rows)


def make_passages(pages, chunk_words=200, overlap_words=40):
    """Cut each page into overlapping passages. A passage never crosses pages, so citations stay exact."""
    rows, step = [], chunk_words - overlap_words
    for p in pages.itertuples():
        words = p.text.split()
        for start in range(0, max(len(words) - overlap_words, 1), step):
            rows.append({"doc": p.doc, "page": p.page, "text": " ".join(words[start:start + chunk_words])})
    passages = pd.DataFrame(rows)
    passages.insert(0, "passage_id", [f"{d}:p{pg}:{i}" for i, (d, pg) in enumerate(zip(passages.doc, passages.page))])
    return passages


def fingerprint(passages):
    """Short hash of the indexed text: changes whenever a document, or the chunking, changes."""
    return hashlib.md5(pd.util.hash_pandas_object(passages[["doc", "page", "text"]], index=False).values.tobytes()).hexdigest()[:12]


class Retriever:
    """Keyword search (TF-IDF with word pairs). Simple, fast, no extra model to download.

    A dense "embedding" retriever (below) finds paraphrases better, and is weaker on exact words: drug names, doses.
    """

    def __init__(self, passages):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.passages = passages.reset_index(drop=True)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, stop_words="english")
        self.matrix = self.vectorizer.fit_transform(self.passages.text)

    def search(self, question, k=5):
        scores = (self.matrix @ self.vectorizer.transform([question]).T).toarray().ravel()
        top = np.argsort(-scores)[:k]
        return self.passages.iloc[top].assign(score=scores[top])


class EmbeddingRetriever:
    """Dense search: passages and question become vectors from a small embedding model; the nearest vectors win.

    Finds passages that say the same thing in other words. The model downloads on first use; embedding all
    passages takes a few minutes on a laptop CPU, once: the vectors are cached in index/.
    """

    def __init__(self, passages, model=EMBED_MODEL):
        from fastembed import TextEmbedding

        self.passages = passages.reset_index(drop=True)
        self.model = TextEmbedding(model, cache_dir=str(INDEX_CACHE / "models"))
        cache = INDEX_CACHE / f"vectors_{model.split('/')[-1]}_{fingerprint(self.passages)}.npy"
        if cache.exists():
            self.matrix = np.load(cache)
        else:
            print(f"embedding {len(self.passages)} passages with {model} (once; a few minutes)...", flush=True)
            m = np.array(list(self.model.passage_embed(self.passages.text.tolist())))
            self.matrix = m / np.linalg.norm(m, axis=1, keepdims=True)
            np.save(cache, self.matrix)

    def search(self, question, k=5):
        q = np.array(next(iter(self.model.query_embed([question]))))
        scores = self.matrix @ (q / np.linalg.norm(q))
        top = np.argsort(-scores)[:k]
        return self.passages.iloc[top].assign(score=scores[top])


def build(settings=Settings(), folder=DOCS):
    """Load (or reuse) the passages for these chunk settings and return a Retriever."""
    INDEX_CACHE.mkdir(exist_ok=True)
    cache = INDEX_CACHE / f"passages_{settings.chunk_words}_{settings.overlap_words}.parquet"
    if cache.exists():
        passages = pd.read_parquet(cache)
    else:
        passages = make_passages(load_pages(folder), settings.chunk_words, settings.overlap_words)
        passages.to_parquet(cache, index=False)
    return EmbeddingRetriever(passages) if settings.retriever == "embed" else Retriever(passages)


# ---------------------------------------------------------------- 2-3. retrieve and generate


def llm_client(async_=False):
    """OpenAI-compatible client for OpenRouter (or LLM_BASE_URL, e.g. a self-hosted vLLM server)."""
    from openai import AsyncOpenAI, OpenAI

    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("no API key: set OPENROUTER_API_KEY (the shared workshop key) and try again")
    base_url = os.environ.get("LLM_BASE_URL", OPENROUTER)
    return (AsyncOpenAI if async_ else OpenAI)(base_url=base_url, api_key=key, timeout=120, max_retries=3)


def thinking_switch(on=False):
    """Extra request arguments that turn a reasoning model's "thinking" on or off.

    Providers spell it differently: OpenRouter takes a `reasoning` object; Ollama and vLLM take
    OpenAI's `reasoning_effort`. Checked on OpenRouter: gemma-4-26b and qwen3.5-9b accept it (0 reasoning
    tokens when off); gpt-oss-120b refuses `enabled: False` (400), so the judge never sends it there.
    """
    if os.environ.get("LLM_BASE_URL", OPENROUTER).startswith(OPENROUTER):
        return {"extra_body": {"reasoning": {"enabled": on}}}
    return {} if on else {"reasoning_effort": "none"}


def format_passages(hits):
    return "\n\n".join(f"[{i}] ({h.doc}, page {h.page}) {h.text}" for i, h in enumerate(hits.itertuples(), 1))


def answer(question, retriever, settings=Settings(), client=None):
    """Retrieve, then generate. Returns the answer plus everything needed to evaluate it."""
    hits = retriever.search(question, settings.k)
    client = client or llm_client()
    t0 = time.time()
    response = client.chat.completions.create(
        model=settings.model,
        temperature=settings.temperature,
        **thinking_switch(settings.thinking),
        messages=[{"role": "system", "content": PROMPTS[settings.prompt_version]},
                  {"role": "user", "content": f"Passages:\n\n{format_passages(hits)}\n\nQuestion: {question}"}],
    )
    return {
        "question": question,
        "answer": (response.choices[0].message.content or "").strip(),
        "contexts": hits.text.tolist(),
        "sources": [f"{d}:p{p}" for d, p in zip(hits.doc, hits.page)],
        "seconds": round(time.time() - t0, 2),
        "tokens": getattr(response.usage, "total_tokens", None),
        "settings": asdict(settings),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--model", default=Settings.model)
    ap.add_argument("--k", type=int, default=Settings.k)
    ap.add_argument("--retriever", default=Settings.retriever, choices=["tfidf", "embed"])
    ap.add_argument("--search-only", action="store_true", help="show the retrieved passages; no LLM call")
    a = ap.parse_args()
    s = Settings(model=a.model, k=a.k, retriever=a.retriever)
    retriever = build(s)
    titles = document_titles()
    hits = retriever.search(a.question, s.k)
    for i, h in enumerate(hits.itertuples(), 1):
        print(f"[{i}] {titles.get(h.doc, h.doc)}, page {h.page} (score {h.score:.3f})\n    {h.text[:220]}...\n")
    if not a.search_only:
        print(answer(a.question, retriever, s)["answer"])


if __name__ == "__main__":
    main()
