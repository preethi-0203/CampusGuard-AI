import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List

from backend.services.auth_service import get_current_user
from backend.services.rag_service import (
    load_documents,
    retrieve_documents
)

router = APIRouter(
    prefix="/assistant",
    tags=["AI Assistant"]
)


class ChatMessage(BaseModel):
    role: str
    text: str


class Question(BaseModel):
    question: str
    history: List[ChatMessage] = Field(default_factory=list)


def topic_match(question, document):
    q = question.lower()
    d = document.lower()

    topics = {
        "sos": [
            "sos",
            "emergency sos",
            "immediate assistance"
        ],

        "incident": [
            "incident",
            "report",
            "reporting",
            "fall",
            "medical",
            "suspicious",
            "suspicious activity"
        ],

        "restricted": [
            "restricted",
            "restricted area",
            "unauthorized entry",
            "enter restricted"
        ],

        "after_hours": [
            "after hours",
            "after-hours",
            "college hours",
            "campus hours",
            "campus timings",
            "timings"
        ],

        "emergency_response": [
            "emergency alert",
            "emergency alerts",
            "security personnel",
            "respond",
            "acknowledge",
            "escalated"
        ]
    }

    for keywords in topics.values():
        question_match = any(
            re.search(r"\b" + re.escape(keyword) + r"\b", q)
            for keyword in keywords
        )

        document_match = any(
            re.search(r"\b" + re.escape(keyword) + r"\b", d)
            for keyword in keywords
        )

        if question_match and document_match:
            return True

    return False


@router.post("/ask")
def ask_question(
    data: Question,
    user=Depends(get_current_user)
):
    question = data.question.strip()

    if not question:
        return {
            "question": question,
            "answer": "Please enter a question.",
            "sources": []
        }

    # Safely load and retrieve campus documents
    try:
        load_documents()
        documents = retrieve_documents(
            question,
            limit=3
        )
    except Exception as exc:
        print(f"Error during document retrieval: {exc}")
        return {
            "question": question,
            "answer": "Unable to retrieve campus safety documents at this time. If this is an emergency, please use the SOS button or contact campus security directly.",
            "sources": []
        }

    if not documents:
        return {
            "question": question,
            "answer": "No relevant campus safety information was found in the campus documents.",
            "sources": []
        }

    # --------------------------------------------------
    # Apply whole-word topic match as score boost (not unconditional override)
    # --------------------------------------------------
    boosted_documents = []
    for doc in documents:
        raw_score = float(doc.get("score", 0.0))
        is_match = topic_match(question, doc.get("text", ""))
        boost = 1.5 if is_match else 0.0
        effective_score = raw_score + boost
        boosted_documents.append({
            **doc,
            "effective_score": effective_score,
            "topic_matched": is_match
        })

    # Sort documents by effective boosted score
    boosted_documents.sort(key=lambda d: d["effective_score"], reverse=True)

    # --------------------------------------------------
    # Relevance rule: documents with effective_score >= 0.0
    # --------------------------------------------------
    relevant_documents = [
        doc for doc in boosted_documents
        if doc["effective_score"] >= 0.0
    ]

    # If no relevant documents pass the relevance rule, return honest "no information found"
    if not relevant_documents:
        return {
            "question": question,
            "answer": "No relevant campus safety information was found in the campus documents.",
            "sources": []
        }

    # --------------------------------------------------
    # Use ALL retrieved sections passing relevance rule as context
    # --------------------------------------------------
    context_sections = [doc["text"].strip() for doc in relevant_documents]
    combined_context = "\n\n---\n\n".join(context_sections)

    sources = [
        {
            "file": doc.get("source", ""),
            "section": doc.get("heading", ""),
            "score": round(
                float(doc.get("score", 0.0)),
                4
            )
        }
        for doc in relevant_documents
    ]

    # --------------------------------------------------
    # Generate answer via LLM using retrieved context and recent history (up to last 6 turns)
    # --------------------------------------------------
    answer = None
    try:
        from backend.services.gemini_service import generate_answer

        recent_history = []
        if data.history:
            for item in data.history[-6:]:
                if isinstance(item, ChatMessage):
                    recent_history.append({"role": item.role, "text": item.text})
                elif isinstance(item, dict):
                    recent_history.append({"role": item.get("role", "user"), "text": item.get("text", "")})
                else:
                    recent_history.append({"role": getattr(item, "role", "user"), "text": getattr(item, "text", "")})

        try:
            llm_response = generate_answer(question, combined_context, history=recent_history)
        except TypeError:
            llm_response = generate_answer(question, combined_context)

        if llm_response:
            lower_response = llm_response.lower()
            if (
                llm_response.startswith("The campus documents do not contain")
                or "do not contain this information" in lower_response
                or "does not contain" in lower_response
            ):
                return {
                    "question": question,
                    "answer": "No relevant campus safety information was found in the campus documents.",
                    "sources": []
                }
            answer = llm_response
    except Exception as exc:
        print(f"Gemini LLM error: {exc}")

    # Clean fallback to verified retrieved document sections if LLM is unavailable / unconfigured
    if not answer:
        answer = "\n\n".join(context_sections)

    return {
        "question": question,
        "answer": answer,
        "sources": sources
    }