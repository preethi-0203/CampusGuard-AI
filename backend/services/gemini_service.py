import os
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None


def generate_answer(question, context, history=None):
    if not client:
        return None

    history_text = ""
    if history:
        recent_turns = history[-6:]
        formatted_turns = []
        for turn in recent_turns:
            if isinstance(turn, dict):
                role = turn.get("role", "user")
                text = turn.get("text", "")
            else:
                role = getattr(turn, "role", "user")
                text = getattr(turn, "text", "")
            formatted_turns.append(f"{role.capitalize()}: {text}")
        if formatted_turns:
            history_text = "\nConversation History:\n" + "\n".join(formatted_turns) + "\n"

    prompt = f"""You are CampusGuard AI, an intelligent campus safety assistant.

Answer the question accurately and concisely using only the context below.
If the answer is not present in the context, state clearly: "The campus documents do not contain this information."

Context:
{context}
{history_text}
Question:
{question}

Answer concisely:"""

    candidate_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as exc:
                err_str = str(exc)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(1)
                    continue
                # If model is not found, break inner loop to try next model
                break

    return None