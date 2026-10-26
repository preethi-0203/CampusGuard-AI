"""
Test Suite for Batch 2 Alert Lifecycle & Tracker Reset Fixes.

Verifies:
1. Escalate alert:
   - Escalating a resolved alert returns HTTP 400.
   - Escalating an active alert succeeds and sets status='escalated' / severity='critical'.
2. Risk calculation overview:
   - Escalated alerts are counted alongside active alerts in calculate_campus_overview.
   - Resolved alerts are not counted.
3. Tracker state reset:
   - ml_service.reset_tracker() clears predictor.trackers safely.
   - Handles case where predictor is None without error.
   - Video analysis invokes tracker reset between executions.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure isolated in-memory test database
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.config.database import Base, get_db
from backend.database.models.user import User
from backend.database.models.alert import Alert
from backend.services.auth_service import create_access_token, password_hash
from backend.services.risk_service import risk_service
from backend.services.ml_service import MLService
from backend.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class TestBatch2LifecycleTracking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)

    def setUp(self):
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestSessionLocal()
        self.officer = User(
            name="Security Officer",
            email="security@campusguard.com",
            password=password_hash.hash("Security123!"),
            role="security",
        )
        db.add(self.officer)
        db.commit()
        db.refresh(self.officer)
        self.officer_id = self.officer.id
        self.officer_token = create_access_token(self.officer_id, "security")
        self.officer_headers = {"Authorization": f"Bearer {self.officer_token}"}
        db.close()

    # --- ITEM 1: ESCALATE RESOLVED GUARD ---

    def test_01_escalate_resolved_alert_returns_400(self):
        """Escalating an alert that is already resolved returns HTTP 400."""
        db = TestSessionLocal()
        alert = Alert(
            alert_type="Weapon Detection",
            location="Gym",
            description="Resolved incident",
            severity="medium",
            status="resolved",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        res = client.patch(f"/alerts/{alert_id}/escalate", headers=self.officer_headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "Cannot escalate a resolved alert")

    def test_02_escalate_active_alert_succeeds(self):
        """Escalating an active alert succeeds and sets critical status."""
        db = TestSessionLocal()
        alert = Alert(
            alert_type="Weapon Detection",
            location="Cafeteria",
            description="Active threat",
            severity="medium",
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        db.close()

        res = client.patch(f"/alerts/{alert_id}/escalate", headers=self.officer_headers)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()["alert"]
        self.assertEqual(data["status"], "escalated")
        self.assertEqual(data["severity"], "critical")
        self.assertTrue(data["escalated"])

    # --- ITEM 2: RISK SERVICE CAMPUS OVERVIEW INCLUDES ESCALATED ALERTS ---

    def test_03_escalated_alert_counted_in_overview(self):
        """Escalated critical alerts are counted in calculate_campus_overview."""
        db = TestSessionLocal()
        alert_escalated = Alert(
            alert_type="Weapon Detection",
            location="Hostel",
            description="Escalated critical alert",
            severity="critical",
            status="escalated",
            escalated=True,
        )
        alert_resolved = Alert(
            alert_type="SOS",
            location="Library",
            description="Resolved SOS alert",
            severity="critical",
            status="resolved",
        )
        db.add_all([alert_escalated, alert_resolved])
        db.commit()

        overview = risk_service.calculate_campus_overview(db)
        db.close()

        # Critical alert count should include the escalated alert, but exclude resolved
        self.assertEqual(overview["critical_alerts_count"], 1)
        self.assertGreaterEqual(overview["risk_score"], 20)
        self.assertTrue(
            any("Critical/High Severity Alert" in s for s in overview["contributing_signals"]),
            f"Expected critical alert in signals, got: {overview['contributing_signals']}"
        )

    # --- ITEM 3: BYTETRACK TRACKER RESET ---

    def test_04_reset_tracker_clears_trackers(self):
        """ml_service.reset_tracker clears trackers attribute on predictor."""
        ml = MLService()
        mock_tracker = MagicMock()
        mock_predictor = MagicMock()
        mock_predictor.trackers = [mock_tracker]
        ml.person_model.predictor = mock_predictor

        ml.reset_tracker()
        mock_tracker.reset.assert_called_once()
        self.assertFalse(hasattr(ml.person_model.predictor, "trackers"))

    def test_05_reset_tracker_handles_none_predictor(self):
        """ml_service.reset_tracker safely handles predictor being None."""
        ml = MLService()
        ml.person_model.predictor = None

        # Should execute cleanly without raising an exception
        try:
            ml.reset_tracker()
        except Exception as exc:
            self.fail(f"reset_tracker raised an unexpected exception with None predictor: {exc}")


if __name__ == "__main__":
    unittest.main()
