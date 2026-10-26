from pathlib import Path
import re

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder


# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
DOCUMENT_DIR = BASE_DIR / "campus_documents"


# --------------------------------------------------
# Models & ChromaDB (Lazy Loaded)
# --------------------------------------------------

_embedding_model = None
_reranker = None
_chroma_client = None
_collection = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def get_collection():
    global _collection, _chroma_client
    if _collection is None:
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_db"))
        _collection = _chroma_client.get_or_create_collection(
            name="campus_documents_hybrid",
            configuration={"hnsw": {"space": "cosine"}}
        )
    return _collection


def __getattr__(name):
    if name == "embedding_model":
        return get_embedding_model()
    if name == "reranker":
        return get_reranker()
    if name == "collection":
        return get_collection()
    if name == "chroma_client":
        if _chroma_client is None:
            get_collection()
        return _chroma_client
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# --------------------------------------------------
# Runtime indexes
# --------------------------------------------------

bm25 = None
indexed_documents = []
documents_loaded = False


# --------------------------------------------------
# Split documents into sections
# --------------------------------------------------

def split_sections(text, source):
    sections = []

    # Split using numbered headings such as:
    # 1. Emergency SOS
    # 2. Incident Reporting
    pattern = r"(?m)^(?P<heading>\d+\.\s+.+)$"

    matches = list(re.finditer(pattern, text))

    if not matches:
        cleaned = text.strip()

        if cleaned:
            sections.append({
                "id": f"{source}_1",
                "text": cleaned,
                "source": source,
                "heading": source
            })

        return sections

    for index, match in enumerate(matches):
        heading = match.group("heading").strip()

        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        section_text = text[start:end].strip()

        if section_text:
            sections.append({
                "id": f"{source}_{index + 1}",
                "text": section_text,
                "source": source,
                "heading": heading
            })

    return sections


# --------------------------------------------------
# Load and index documents
# --------------------------------------------------

def load_documents(force=False):
    global bm25
    global indexed_documents
    global documents_loaded

    if documents_loaded and not force:
        return len(indexed_documents)

    documents = []

    if not DOCUMENT_DIR.exists():
        indexed_documents = []
        bm25 = None
        documents_loaded = True
        return 0

    for file in sorted(DOCUMENT_DIR.rglob("*.txt")):
        try:
            text = file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if text:
            documents.extend(
                split_sections(text, file.stem)
            )

    if not documents:
        indexed_documents = []
        bm25 = None
        documents_loaded = True
        return 0

    ids = [doc["id"] for doc in documents]
    texts = [doc["text"] for doc in documents]

    metadatas = [
        {
            "source": doc["source"],
            "heading": doc["heading"]
        }
        for doc in documents
    ]

    # Create embeddings
    coll = get_collection()
    embeddings = get_embedding_model().encode(
        texts,
        normalize_embeddings=True
    ).tolist()

    # Remove old Chroma records
    try:
        existing = coll.get()

        if existing.get("ids"):
            coll.delete(
                ids=existing["ids"]
            )
    except Exception:
        pass

    # Insert current documents
    coll.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings
    )

    indexed_documents = documents

    # Build BM25 index
    tokenized_documents = [
        re.findall(
            r"\b\w+\b",
            doc["text"].lower()
        )
        for doc in documents
    ]

    bm25 = BM25Okapi(tokenized_documents)

    documents_loaded = True

    return len(documents)


# --------------------------------------------------
# Keyword normalization
# --------------------------------------------------

def normalize_text(text):
    return re.findall(
        r"\b\w+\b",
        text.lower()
    )


# --------------------------------------------------
# Hybrid search
# --------------------------------------------------

def hybrid_search(question, limit=10):
    try:
        if not indexed_documents or bm25 is None:
            load_documents()

        if not indexed_documents or bm25 is None:
            return []

        query_embedding = get_embedding_model().encode(
            [question],
            normalize_embeddings=True
        ).tolist()

        result_count = min(
            max(limit, 5),
            len(indexed_documents)
        )

        semantic_results = get_collection().query(
            query_embeddings=query_embedding,
            n_results=result_count,
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )

        semantic_scores = {}

        if semantic_results.get("ids"):
            ids = semantic_results["ids"][0]
            distances = semantic_results["distances"][0]

            for doc_id, distance in zip(ids, distances):
                semantic_scores[doc_id] = (
                    1 / (1 + max(0, float(distance)))
                )

        # BM25 keyword search
        query_tokens = normalize_text(question)

        keyword_scores = bm25.get_scores(
            query_tokens
        )

        max_keyword = (
            max(keyword_scores)
            if len(keyword_scores)
            else 0
        )

        if max_keyword > 0:
            keyword_scores = (
                keyword_scores / max_keyword
            )

        keyword_map = {
            doc["id"]: float(keyword_scores[index])
            for index, doc in enumerate(indexed_documents)
        }

        # Combine semantic + keyword scores
        combined = []

        for doc in indexed_documents:
            doc_id = doc["id"]

            semantic_score = semantic_scores.get(
                doc_id,
                0
            )

            keyword_score = keyword_map.get(
                doc_id,
                0
            )

            combined_score = (
                0.6 * semantic_score
                + 0.4 * keyword_score
            )

            combined.append(
                (combined_score, doc)
            )

        combined.sort(
            key=lambda item: item[0],
            reverse=True
        )

        return [
            doc
            for score, doc in combined[:limit]
        ]
    except Exception as exc:
        print(f"Error in hybrid_search: {exc}")
        return []


# --------------------------------------------------
# Cross-encoder reranking
# --------------------------------------------------

def retrieve_documents(question, limit=3):
    try:
        candidates = hybrid_search(
            question,
            limit=10
        )

        if not candidates:
            return []

        pairs = [
            (
                question,
                document["text"]
            )
            for document in candidates
        ]

        scores = get_reranker().predict(pairs)

        ranked = sorted(
            zip(scores, candidates),
            key=lambda item: float(item[0]),
            reverse=True
        )

        results = []

        for score, document in ranked[:limit]:
            results.append({
                **document,
                "score": float(score)
            })

        return results
    except Exception as exc:
        print(f"Error in retrieve_documents: {exc}")
        return []


# --------------------------------------------------
# Test
# --------------------------------------------------

if __name__ == "__main__":

    count = load_documents(
        force=True
    )

    print(
        f"Indexed sections: {count}"
    )

    questions = [
        "How do I use the SOS button?",
        "What should I do if I see suspicious activity?",
        "What happens when a student enters a restricted area?",
        "What should students do after campus hours?",
        "Who should respond to emergency alerts?"
    ]

    for question in questions:

        print(
            f"\nQuestion: {question}"
        )

        results = retrieve_documents(
            question,
            limit=3
        )

        for result in results:

            print(
                f"\nSection: {result['heading']}"
            )

            print(
                f"Score: {result['score']:.4f}"
            )

            print(
                result["text"]
            )