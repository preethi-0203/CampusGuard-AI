"""
Isolated Test Suite for Resolution-Aware Restricted Zone Service (Step 11)

Tests:
1. Default zones use normalized coordinates (0.0 to 1.0).
2. Equivalent detection across multiple frame resolutions (1080p, 720p, 480p, 4K, 800x600).
3. Persons inside and outside configured zones.
4. Inclusive boundary coordinates and adjacent outside points.
5. Missing or invalid frame dimensions handled safely without exceptions.
6. Missing or invalid person coordinates (None, NaN, Inf, string) handled safely.
7. Frame object input handling via frame.shape.
8. Custom, legacy pixel-based, inverted, and malformed zone configurations.
9. Image and video pipeline compatibility and unified zone logic.
"""

import sys
import os
from pathlib import Path
import unittest
import numpy as np
import math

# Ensure project root is in sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from unittest.mock import MagicMock, patch

from backend.services.restricted_zone_service import (
    RestrictedZoneService,
    DEFAULT_ZONES,
    DEFAULT_REFERENCE_RESOLUTION,
)


class TestRestrictedZoneService(unittest.TestCase):
    def setUp(self):
        self.service = RestrictedZoneService()

    def test_01_default_zones_normalized(self):
        """Default zones must be normalized between 0.0 and 1.0 with x1 <= x2 and y1 <= y2."""
        self.assertIn("Restricted Area", self.service.zones)
        zone = self.service.zones["Restricted Area"]

        self.assertGreaterEqual(zone["x1"], 0.0)
        self.assertLessEqual(zone["x1"], 1.0)
        self.assertGreaterEqual(zone["x2"], 0.0)
        self.assertLessEqual(zone["x2"], 1.0)
        self.assertGreaterEqual(zone["y1"], 0.0)
        self.assertLessEqual(zone["y1"], 1.0)
        self.assertGreaterEqual(zone["y2"], 0.0)
        self.assertLessEqual(zone["y2"], 1.0)

        self.assertLessEqual(zone["x1"], zone["x2"])
        self.assertLessEqual(zone["y1"], zone["y2"])

        # Derived from legacy bounds: ~0.052 horizontal, ~0.833 vertical
        self.assertAlmostEqual(zone["x1"], 100.0 / 1920.0, places=3)
        self.assertAlmostEqual(zone["x2"], 400.0 / 1920.0, places=3)
        self.assertAlmostEqual(zone["y1"], 900.0 / 1080.0, places=3)
        self.assertEqual(zone["y2"], 1.0)

    def test_02_multiple_resolutions_equivalent_detection(self):
        """
        A person at the same relative position (norm_x=0.15, norm_y=0.90) must be
        detected across multiple resolutions: 1080p, 720p, 480p, 4K, and 800x600.
        A person at the frame center (norm_x=0.50, norm_y=0.50) must not be detected.
        """
        resolutions = [
            (1920, 1080),  # Full HD
            (1280, 720),   # 720p HD
            (640, 480),    # 480p SD / VGA
            (3840, 2160),  # 4K UHD
            (800, 600),    # SVGA
        ]

        norm_inside_x, norm_inside_y = 0.15, 0.90
        norm_outside_x, norm_outside_y = 0.50, 0.50

        for width, height in resolutions:
            with self.subTest(resolution=f"{width}x{height}"):
                # Inside point converted to current frame resolution
                inside_px = norm_inside_x * width
                inside_py = norm_inside_y * height
                res_inside = self.service.check_person(
                    inside_px, inside_py, frame_width=width, frame_height=height
                )
                self.assertTrue(
                    res_inside["restricted_entry"],
                    f"Failed to detect person inside zone at {width}x{height} (pixel: {inside_px}, {inside_py})",
                )
                self.assertEqual(res_inside["zone"], "Restricted Area")
                self.assertEqual(res_inside["message"], "Person detected in restricted area")

                # Outside point converted to current frame resolution
                outside_px = norm_outside_x * width
                outside_py = norm_outside_y * height
                res_outside = self.service.check_person(
                    outside_px, outside_py, frame_width=width, frame_height=height
                )
                self.assertFalse(
                    res_outside["restricted_entry"],
                    f"False positive for person outside zone at {width}x{height} (pixel: {outside_px}, {outside_py})",
                )
                self.assertIsNone(res_outside["zone"])
                self.assertEqual(res_outside["message"], "No restricted-zone entry detected")

    def test_03_boundary_coordinates(self):
        """Boundary points on the zone edges must be considered inside (inclusive bounds)."""
        width, height = 1920, 1080
        zone = self.service.zones["Restricted Area"]
        pixel_zone = self.service.get_zone_pixels(zone, width, height)

        zx1, zx2 = pixel_zone["x1"], pixel_zone["x2"]
        zy1, zy2 = pixel_zone["y1"], pixel_zone["y2"]

        # 4 corners (exact boundaries)
        corners = [
            (zx1, zy1),
            (zx2, zy1),
            (zx1, zy2),
            (zx2, zy2),
        ]
        for bx, by in corners:
            res = self.service.check_person(bx, by, frame_width=width, frame_height=height)
            self.assertTrue(res["restricted_entry"], f"Corner ({bx}, {by}) should be inside boundary")

        # Points just outside boundaries
        just_outside = [
            (zx1 - 2.0, (zy1 + zy2) / 2),  # Left of zone
            (zx2 + 2.0, (zy1 + zy2) / 2),  # Right of zone
            ((zx1 + zx2) / 2, zy1 - 2.0),  # Above zone
            ((zx1 + zx2) / 2, zy2 + 2.0),  # Below zone
        ]
        for ox, oy in just_outside:
            res = self.service.check_person(ox, oy, frame_width=width, frame_height=height)
            self.assertFalse(res["restricted_entry"], f"Point ({ox}, {oy}) should be outside boundary")

    def test_04_missing_and_invalid_frame_dimensions(self):
        """Missing or invalid frame dimensions must be handled safely without exceptions."""
        invalid_dimensions = [
            (None, None),
            (0, 1080),
            (1920, 0),
            (-1920, 1080),
            (1920, -1080),
            ("1920", None),
            (float("nan"), 1080),
            (1920, float("inf")),
        ]

        # Using pixel coordinates that require frame dimensions
        pixel_x, pixel_y = 200, 950

        for fw, fh in invalid_dimensions:
            with self.subTest(dim=(fw, fh)):
                res = self.service.check_person(pixel_x, pixel_y, frame_width=fw, frame_height=fh)
                self.assertIsInstance(res, dict)
                self.assertFalse(res["restricted_entry"])
                self.assertIsNone(res["zone"])

    def test_05_missing_and_invalid_person_coordinates(self):
        """Invalid person coordinates (None, NaN, Inf, non-numeric) must return safe default."""
        invalid_coords = [
            (None, None),
            (None, 500),
            (500, None),
            (float("nan"), 500),
            (500, float("nan")),
            (float("inf"), 500),
            (500, float("-inf")),
            ("invalid", 500),
            (500, "invalid"),
        ]

        for px, py in invalid_coords:
            with self.subTest(coords=(px, py)):
                res = self.service.check_person(px, py, frame_width=1920, frame_height=1080)
                self.assertIsInstance(res, dict)
                self.assertFalse(res["restricted_entry"])
                self.assertIsNone(res["zone"])

    def test_06_numpy_frame_object_input(self):
        """Passing a numpy array frame directly should extract dimensions and evaluate correctly."""
        # Create dummy 720p frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Inside person on 720p
        inside_x = 0.15 * 1280
        inside_y = 0.90 * 720
        res_inside = self.service.check_person(inside_x, inside_y, frame=frame)
        self.assertTrue(res_inside["restricted_entry"])
        self.assertEqual(res_inside["zone"], "Restricted Area")

        # Outside person on 720p
        outside_x = 0.50 * 1280
        outside_y = 0.50 * 720
        res_outside = self.service.check_person(outside_x, outside_y, frame=frame)
        self.assertFalse(res_outside["restricted_entry"])

        # Invalid frame object (1D array)
        invalid_frame = np.zeros((10,), dtype=np.uint8)
        res_invalid = self.service.check_person(inside_x, inside_y, frame=invalid_frame)
        self.assertFalse(res_invalid["restricted_entry"])

    def test_07_custom_and_legacy_zone_configurations(self):
        """Service must handle custom normalized zones, legacy pixel zones, and malformed zones."""
        # 1. Custom normalized zone
        custom_zones = {
            "Server Room Area": {
                "x1": 0.60,
                "y1": 0.10,
                "x2": 0.90,
                "y2": 0.40,
            }
        }
        custom_service = RestrictedZoneService(zones=custom_zones)
        self.assertIn("Server Room Area", custom_service.zones)

        res = custom_service.check_person(0.75, 0.25, frame_width=1000, frame_height=1000)
        # Note: 0.75 * 1000 = 750, 0.25 * 1000 = 250
        res_pixel = custom_service.check_person(750, 250, frame_width=1000, frame_height=1000)
        self.assertTrue(res_pixel["restricted_entry"])
        self.assertEqual(res_pixel["zone"], "Server Room Area")

        # 2. Legacy pixel zone definition auto-normalized
        legacy_zones = {
            "Legacy Zone": {
                "x1": 100,
                "y1": 900,
                "x2": 400,
                "y2": 1150,
            }
        }
        legacy_service = RestrictedZoneService(zones=legacy_zones, reference_resolution=(1920, 1080))
        self.assertIn("Legacy Zone", legacy_service.zones)
        norm_legacy = legacy_service.zones["Legacy Zone"]
        self.assertAlmostEqual(norm_legacy["x1"], 100.0 / 1920.0, places=3)
        self.assertEqual(norm_legacy["y2"], 1.0)  # Clamped to 1.0

        # 3. Inverted zone coordinates (x1 > x2 or y1 > y2)
        inverted_zones = {
            "Inverted Zone": {
                "x1": 0.80,
                "y1": 0.90,
                "x2": 0.20,
                "y2": 0.10,
            }
        }
        inverted_service = RestrictedZoneService(zones=inverted_zones)
        inv = inverted_service.zones["Inverted Zone"]
        self.assertEqual(inv["x1"], 0.20)
        self.assertEqual(inv["x2"], 0.80)
        self.assertEqual(inv["y1"], 0.10)
        self.assertEqual(inv["y2"], 0.90)

        # 4. Malformed zone definitions skipped safely
        malformed_zones = {
            "Missing Keys": {"x1": 0.1, "y1": 0.2},
            "Non-Numeric": {"x1": "abc", "y1": 0.1, "x2": 0.5, "y2": 0.5},
            "Valid Zone": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
        }
        malformed_service = RestrictedZoneService(zones=malformed_zones)
        self.assertEqual(len(malformed_service.zones), 1)
        self.assertIn("Valid Zone", malformed_service.zones)

        # 5. Empty zones dict
        empty_service = RestrictedZoneService(zones={})
        self.assertEqual(len(empty_service.zones), 0)
        res_empty = empty_service.check_person(100, 100, frame_width=1000, frame_height=1000)
        self.assertFalse(res_empty["restricted_entry"])

    def test_08_normalized_direct_evaluation_without_dimensions(self):
        """When coordinates are already normalized (0.0 <= x, y <= 1.0), check_person evaluates directly."""
        res_inside = self.service.check_person(0.15, 0.90)
        self.assertTrue(res_inside["restricted_entry"])
        self.assertEqual(res_inside["zone"], "Restricted Area")

        res_outside = self.service.check_person(0.50, 0.50)
        self.assertFalse(res_outside["restricted_entry"])

    def test_09_ml_service_image_and_video_unified_logic(self):
        """Verify MLService integrates RestrictedZoneService with frame dimensions in both image and video."""
        from backend.services.ml_service import MLService
        ml = MLService()

        # Both methods use the same self.zone_service instance
        self.assertIsInstance(ml.zone_service, RestrictedZoneService)

        # Test zone_service inside ml_service detects across resolutions
        for w, h in [(640, 480), (1280, 720), (1920, 1080)]:
            x = 0.15 * w
            y = 0.90 * h
            res = ml.zone_service.check_person(x, y, frame_width=w, frame_height=h)
            self.assertTrue(res["restricted_entry"])

    def test_10_portrait_and_legacy_cctv_resolutions(self):
        """Test portrait resolution (1080x1920) and legacy CCTV resolutions (704x480, 720x576)."""
        resolutions = [
            (1080, 1920),  # Portrait (9:16 mobile CCTV / vertical video)
            (704, 480),    # Legacy CCTV 4CIF / D1 NTSC
            (720, 576),    # Legacy CCTV 4CIF / D1 PAL
        ]

        norm_inside_x, norm_inside_y = 0.15, 0.90
        norm_outside_x, norm_outside_y = 0.50, 0.50

        for width, height in resolutions:
            with self.subTest(resolution=f"{width}x{height}"):
                # Inside point
                inside_px = norm_inside_x * width
                inside_py = norm_inside_y * height
                res_inside = self.service.check_person(
                    inside_px, inside_py, frame_width=width, frame_height=height
                )
                self.assertTrue(
                    res_inside["restricted_entry"],
                    f"Expected restricted entry at {width}x{height} ({inside_px}, {inside_py})",
                )
                self.assertEqual(res_inside["zone"], "Restricted Area")

                # Outside point
                outside_px = norm_outside_x * width
                outside_py = norm_outside_y * height
                res_outside = self.service.check_person(
                    outside_px, outside_py, frame_width=width, frame_height=height
                )
                self.assertFalse(
                    res_outside["restricted_entry"],
                    f"False positive outside zone at {width}x{height} ({outside_px}, {outside_py})",
                )
                self.assertIsNone(res_outside["zone"])

    @patch("backend.services.ml_service.YOLO")
    @patch("backend.services.ml_service.WeaponDetection")
    @patch("backend.services.ml_service.FightDetection")
    @patch("backend.services.ml_service.FallDetection")
    def test_11_multiple_people_mixed_presence_mocked(self, mock_fall, mock_fight, mock_weapon, mock_yolo):
        """Test multiple people in one frame, with one inside and one outside the restricted zone, using mocks."""
        from backend.services.ml_service import MLService
        ml = MLService()

        # Mock person_model.predict returning 2 boxes:
        # Box 1 (outside): [500, 300, 600, 500] -> feet at (550, 500)
        # Box 2 (inside): [150, 800, 250, 950] -> feet at (200, 950) inside default zone [100..400 x 900..1080]
        mock_result = MagicMock()
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu().numpy.return_value = np.array([
            [500, 300, 600, 500],
            [150, 800, 250, 950],
        ])
        mock_result.boxes = mock_boxes
        ml.person_model.predict.return_value = [mock_result]
        ml.fall_detector.detect.return_value = False
        ml.fight_detector.detect.return_value = False
        ml.weapon_detector.detect.return_value = []

        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        res = ml.analyze_frame(dummy_frame)

        self.assertEqual(res["person_count"], 2)
        self.assertEqual(len(res["people"]), 2)
        self.assertTrue(res["restricted_entry"])
        self.assertEqual(res["restricted_zone"], "Restricted Area")

        # Verify the two people bounding boxes
        self.assertEqual(res["people"][0], {"x1": 500, "y1": 300, "x2": 600, "y2": 500})
        self.assertEqual(res["people"][1], {"x1": 150, "y1": 800, "x2": 250, "y2": 950})

    @patch("backend.services.ml_service.YOLO")
    @patch("backend.services.ml_service.WeaponDetection")
    @patch("backend.services.ml_service.FightDetection")
    @patch("backend.services.ml_service.FallDetection")
    def test_12_empty_and_invalid_frames_in_ml_service(self, mock_fall, mock_fight, mock_weapon, mock_yolo):
        """Empty or invalid frames must return safe defaults without executing model inference."""
        from backend.services.ml_service import MLService
        ml = MLService()

        invalid_frames = [
            None,
            np.zeros((0, 0, 3), dtype=np.uint8),
            np.zeros((10,), dtype=np.uint8),
            "invalid_string",
        ]

        for frame in invalid_frames:
            with self.subTest(frame=type(frame)):
                res = ml.analyze_frame(frame)
                self.assertIsInstance(res, dict)
                self.assertEqual(res["person_count"], 0)
                self.assertEqual(res["people"], [])
                self.assertFalse(res["restricted_entry"])
                self.assertIsNone(res["restricted_zone"])
                self.assertFalse(res["fall_detected"])
                self.assertFalse(res["weapon_detected"])

        # Model predict should not have been called for invalid frames
        ml.person_model.predict.assert_not_called()


if __name__ == "__main__":
    unittest.main()
