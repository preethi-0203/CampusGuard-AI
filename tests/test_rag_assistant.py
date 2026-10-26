import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.services.auth_service import password_hash, create_access_token

from sqlalchemy.pool import StaticPool

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class TestRAGAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=test_engine)
        db = TestSessionLocal()
        cls.test_user = User(
            name="RAG Test Student",
            email="rag_test_student@campusguard.com",
            password=password_hash.hash("RAGPass123!"),
            role="student",
        )
        db.add(cls.test_user)
        db.commit()
        db.refresh(cls.test_user)
        cls.user_id = cls.test_user.id
        db.close()

        cls.token = create_access_token(cls.user_id, "student")
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db

    # 1. Campus emergency procedures retrieval
    def test_01_emergency_sos_retrieval(self):
        """Emergency SOS query retrieves relevant safety documentation with source metadata and positive score."""
        res = client.post(
            "/assistant/ask",
            json={"question": "How do I report an emergency using the SOS button?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("answer", data)
        self.assertTrue(len(data["answer"]) > 10)
        self.assertIn("SOS", data["answer"])
        self.assertIn("sources", data)
        self.assertTrue(len(data["sources"]) > 0)

        source = data["sources"][0]
        self.assertIn("file", source)
        self.assertIn("section", source)
        self.assertIn("Emergency SOS", source["section"])
        self.assertIsInstance(source["score"], (int, float))

    # 2. Incident reporting retrieval
    def test_02_incident_reporting_retrieval(self):
        """Incident reporting query retrieves reporting guidance from campus documents."""
        res = client.post(
            "/assistant/ask",
            json={"question": "What should I do if I notice suspicious activity on campus?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("answer", data)
        self.assertTrue(len(data["sources"]) > 0)
        source = data["sources"][0]
        self.assertIn("Incident Reporting", source["section"])

    # 3. Restricted area retrieval
    def test_03_restricted_area_retrieval(self):
        """Restricted area query retrieves restricted area safety policy."""
        res = client.post(
            "/assistant/ask",
            json={"question": "What happens if a student enters a restricted area without authorization?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("answer", data)
        self.assertTrue(len(data["sources"]) > 0)
        source = data["sources"][0]
        self.assertIn("Restricted Area", source["section"])

    # 4. Unrelated question does not receive a fabricated answer
    def test_04_unrelated_question_no_fabricated_answer(self):
        """Unrelated questions (e.g. general knowledge, recipes) do not receive fabricated policy answers."""
        unrelated_questions = [
            "What is the capital of France?",
            "How do I bake chocolate chip cookies?",
            "Who won the 1998 World Cup?",
        ]
        for q in unrelated_questions:
            res = client.post(
                "/assistant/ask",
                json={"question": q},
                headers=self.auth_headers,
            )
            self.assertEqual(res.status_code, 200, res.text)
            data = res.json()
            self.assertEqual(
                data["answer"],
                "No relevant campus safety information was found in the campus documents."
            )
            self.assertEqual(data["sources"], [])

    # 5. LLM negative response handled honestly without dumping irrelevant text
    @patch("backend.services.gemini_service.generate_answer")
    def test_05_llm_negative_response_returns_no_information(self, mock_llm):
        """When LLM indicates context does not answer the question, returns no information found rather than dumping irrelevant section."""
        mock_llm.return_value = "The campus documents do not contain this information."

        res = client.post(
            "/assistant/ask",
            json={"question": "What is the emergency phone number for the London subway?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(
            data["answer"],
            "No relevant campus safety information was found in the campus documents."
        )
        self.assertEqual(data["sources"], [])

    # 6. LLM offline or failure cleanly falls back to retrieved section
    @patch("backend.services.gemini_service.generate_answer", side_effect=Exception("Simulated LLM Timeout"))
    def test_06_llm_failure_falls_back_to_retrieved_section(self, mock_llm):
        """When LLM is unavailable or fails, system cleanly falls back to verified retrieved document section."""
        res = client.post(
            "/assistant/ask",
            json={"question": "How do I use the emergency SOS button?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("Emergency SOS", data["answer"])
        self.assertTrue(len(data["sources"]) > 0)
        self.assertIn("file", data["sources"][0])

    # 7. Embedding/retrieval failure handled safely without 500 error
    @patch("backend.routes.assistant.retrieve_documents", side_effect=RuntimeError("Simulated Vector DB Crash"))
    def test_07_embedding_retrieval_failure_handled_safely(self, mock_retrieve):
        """When vector database or embedding model crashes, endpoint safely returns user-friendly fallback."""
        res = client.post(
            "/assistant/ask",
            json={"question": "How do I report an emergency?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn("Unable to retrieve campus safety documents", data["answer"])
        self.assertEqual(data["sources"], [])

    # 8. Empty retrieval results handled safely
    @patch("backend.routes.assistant.retrieve_documents", return_value=[])
    def test_08_empty_retrieval_results_handled_safely(self, mock_retrieve):
        """When retrieval returns no documents, endpoint cleanly returns no information found."""
        res = client.post(
            "/assistant/ask",
            json={"question": "Is there any information about campus shuttles?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(
            data["answer"],
            "No relevant campus safety information was found in the campus documents."
        )
        self.assertEqual(data["sources"], [])

    # 9. Empty question input handled cleanly
    def test_09_empty_question_handling(self):
        """Empty or whitespace-only questions prompt the user to enter a question."""
        res = client.post(
            "/assistant/ask",
            json={"question": "   "},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["answer"], "Please enter a question.")
        self.assertEqual(data["sources"], [])

    # 10. API response contract matches frontend expectations
    def test_10_api_response_contract_matches_frontend(self):
        """Verifies API response structure strictly satisfies frontend AssistantPage component contract."""
        res = client.post(
            "/assistant/ask",
            json={"question": "Who should respond to emergency alerts?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Frontend expects: data.answer (or data.response/message), and data.sources
        self.assertIn("answer", data)
        self.assertIsInstance(data["answer"], str)
        self.assertIn("sources", data)
        self.assertIsInstance(data["sources"], list)

        if data["sources"]:
            source = data["sources"][0]
            # Frontend App.jsx reads: source.file, source.section, source.score
            self.assertIn("file", source)
            self.assertIsInstance(source["file"], str)
            self.assertIn("section", source)
            self.assertIsInstance(source["section"], str)
            self.assertIn("score", source)
            self.assertIsInstance(source["score"], (int, float))

    # 11. Unauthenticated access rejected
    def test_11_unauthenticated_request_rejected(self):
        """Unauthenticated requests without a token are rejected with 401 Unauthorized."""
        res = client.post(
            "/assistant/ask",
            json={"question": "How do I report an incident?"},
        )
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
