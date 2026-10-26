import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.database.models.incident import Incident
from backend.services.auth_service import password_hash, create_access_token
from backend.services.nlp_service import nlp_service
from backend.routes.assistant import topic_match

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


class TestBatch3NLPAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=test_engine)
        db = TestSessionLocal()
        cls.test_officer = User(
            name="Batch3 Officer",
            email="batch3_officer@campusguard.com",
            password=password_hash.hash("SecurePass123!"),
            role="security",
        )
        db.add(cls.test_officer)
        db.commit()
        db.refresh(cls.test_officer)
        cls.officer_id = cls.test_officer.id
        db.close()

        cls.token = create_access_token(cls.officer_id, "security")
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    # 1. NLP Service: "A man attacked me" -> High urgency
    def test_01_man_attacked_me_high_urgency(self):
        res = nlp_service.analyze_report("A man attacked me")
        self.assertEqual(res["urgency"], "High")
        self.assertEqual(res["category"], "Fighting")

    # 2. NLP Service: "man with a gun threatening someone" -> Weapon category
    def test_02_gun_threat_weapon_category(self):
        res = nlp_service.analyze_report("man with a gun threatening someone")
        self.assertEqual(res["category"], "Weapon")
        self.assertEqual(res["urgency"], "High")

    # 3. NLP Service: Weapon checked before Fighting
    def test_03_weapon_prioritized_over_fighting(self):
        # Text contains both weapon and fighting keywords
        res = nlp_service.analyze_report("A man with a gun attacked someone")
        self.assertEqual(res["category"], "Weapon")
        self.assertEqual(res["urgency"], "High")

    # 4. NLP Service: "I hit a pothole" not Fighting
    def test_04_hit_pothole_not_fighting(self):
        res = nlp_service.analyze_report("I hit a pothole")
        self.assertNotEqual(res["category"], "Fighting")
        self.assertEqual(res["category"], "Other")
        self.assertEqual(res["urgency"], "Normal")

    # 5. NLP Service: Additional urgent word stems (assault, knives)
    def test_05_urgent_stems_and_words(self):
        res1 = nlp_service.analyze_report("Someone assaulted a student")
        self.assertEqual(res1["urgency"], "High")

        res2 = nlp_service.analyze_report("A suspect was seen carrying knives")
        self.assertEqual(res2["urgency"], "High")
        self.assertEqual(res2["category"], "Weapon")

    # 6. Assistant: "waterfall" does not trigger the fall topic
    def test_06_waterfall_does_not_trigger_fall_topic(self):
        doc_text = "Students can report falls, medical emergencies, and other safety incidents."
        self.assertFalse(topic_match("waterfall", doc_text))
        self.assertFalse(topic_match("There is a beautiful waterfall on campus", doc_text))
        # Whole-word fall DOES match
        self.assertTrue(topic_match("A student had a slip and fall", doc_text))

    # 7. Assistant: Follow-up question uses history and passes up to last 6 turns
    @patch("backend.routes.assistant.retrieve_documents")
    @patch("backend.services.gemini_service.generate_answer")
    def test_07_followup_question_passes_history(self, mock_llm, mock_retrieve):
        mock_retrieve.return_value = [
            {"id": "doc_1", "text": "1. Emergency SOS guidance", "source": "campus_safety", "heading": "1. Emergency SOS", "score": 2.5}
        ]
        mock_llm.return_value = "Follow-up response based on conversation history."

        history_payload = [
            {"role": "user", "text": "Turn 1: How do I report an emergency?"},
            {"role": "assistant", "text": "Turn 2: Press the SOS button."},
            {"role": "user", "text": "Turn 3: Where is the SOS button?"},
            {"role": "assistant", "text": "Turn 4: On the student dashboard."},
            {"role": "user", "text": "Turn 5: What if I am off campus?"},
            {"role": "assistant", "text": "Turn 6: Contact emergency services directly."},
            {"role": "user", "text": "Turn 7: Thank you!"},
            {"role": "assistant", "text": "Turn 8: You're welcome."},
        ]

        res = client.post(
            "/assistant/ask",
            json={
                "question": "Can you repeat where the SOS button is?",
                "history": history_payload
            },
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(mock_llm.called)

        # Check history passed to mock_llm
        call_kwargs = mock_llm.call_args[1]
        passed_history = call_kwargs.get("history")
        self.assertIsNotNone(passed_history)
        # Should be capped at last 6 turns
        self.assertEqual(len(passed_history), 6)
        self.assertEqual(passed_history[0]["text"], "Turn 3: Where is the SOS button?")
        self.assertEqual(passed_history[-1]["text"], "Turn 8: You're welcome.")

    # 8. Assistant: Multiple sources returned when multiple sections pass relevance rule
    @patch("backend.routes.assistant.retrieve_documents")
    def test_08_multiple_sources_returned(self, mock_retrieve):
        mock_retrieve.return_value = [
            {"id": "doc_1", "text": "1. Emergency SOS guidance", "source": "campus_safety", "heading": "1. Emergency SOS", "score": 2.5},
            {"id": "doc_2", "text": "5. Emergency Alerts response", "source": "campus_safety", "heading": "5. Emergency Alerts", "score": 1.2},
            {"id": "doc_3", "text": "3. Restricted Areas policy", "source": "safety_guidelines", "heading": "3. Restricted Areas", "score": -3.0},
        ]

        res = client.post(
            "/assistant/ask",
            json={"question": "What is the emergency protocol?"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        # The first two documents pass the relevance rule (effective_score >= 0.0)
        self.assertGreaterEqual(len(data["sources"]), 2)
        source_headings = [s["section"] for s in data["sources"]]
        self.assertIn("1. Emergency SOS", source_headings)
        self.assertIn("5. Emergency Alerts", source_headings)

    # 9. Alerts Promote Route: Casing is High/Normal and comparison is case-insensitive
    def test_09_alerts_promote_casing_and_case_insensitive(self):
        db = TestSessionLocal()
        # Create critical alert
        alert = Alert(
            alert_type="Weapon Detection",
            location="Science Block - South",
            severity="critical",
            status="active",
            description="Person spotted with weapon"
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        res = client.post(
            f"/alerts/{alert_id}/promote-to-incident",
            json={"notes": "Investigating immediately"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        incident_id = data["incident_id"]

        db = TestSessionLocal()
        incident = db.query(Incident).filter_by(id=incident_id).first()
        self.assertIsNotNone(incident)
        # Should be capitalized "High" (not lowercase "high")
        self.assertEqual(incident.nlp_urgency, "High")
        db.close()


if __name__ == "__main__":
    unittest.main()
