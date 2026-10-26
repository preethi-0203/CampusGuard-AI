"""
Restricted Zone Service

Provides resolution-aware restricted zone monitoring for CampusGuard AI CCTV analysis.
Converts normalized coordinates (0.0 to 1.0) to frame-specific pixel coordinates during
person tracking and static frame inspection.

Note on Campus Zones:
The default "Restricted Area" coordinates are normalized representations (0.0 - 1.0)
derived from the demonstration boundary [100..400 x 900..1150] at 1920x1080 reference resolution.
These default coordinates represent an illustrative demonstration geofence (lower-left quadrant)
and do not depict actual physical campus building layouts or real campus security zones.
For live deployment, camera-specific geofence polygons/bounding boxes should be calibrated
to the optical coverage of each installed sensor.
"""

import math


DEFAULT_REFERENCE_RESOLUTION = (1920, 1080)

DEFAULT_ZONES = {
    "Restricted Area": {
        # Normalized bounding box coordinates (0.0 to 1.0 relative to frame width and height)
        # Based on default lower-left zone reference [x: 100/1920..400/1920, y: 900/1080..1.0]
        "x1": round(100.0 / 1920.0, 4),  # 0.0521
        "y1": round(900.0 / 1080.0, 4),  # 0.8333
        "x2": round(400.0 / 1920.0, 4),  # 0.2083
        "y2": 1.0,                       # Frame bottom boundary
    }
}


class RestrictedZoneService:
    def __init__(self, zones=None, reference_resolution=DEFAULT_REFERENCE_RESOLUTION):
        """
        Initialize the RestrictedZoneService.

        Parameters:
            zones (dict, optional): Mapping of zone name to coordinate dicts.
                                   Coordinates can be normalized (0.0-1.0) or pixel values
                                   relative to reference_resolution.
            reference_resolution (tuple, optional): (width, height) fallback for legacy pixel zones.
        """
        self.reference_resolution = reference_resolution
        self.zones = {}

        zone_source = zones if zones is not None else DEFAULT_ZONES
        if isinstance(zone_source, dict):
            for name, zone in zone_source.items():
                norm = self._validate_and_normalize_zone(zone)
                if norm is not None:
                    self.zones[str(name)] = norm

    def _validate_and_normalize_zone(self, zone):
        """
        Validate and convert zone boundaries to normalized [0.0, 1.0] floats.
        Returns None if zone configuration is malformed.
        """
        if not isinstance(zone, dict):
            return None

        required_keys = ("x1", "y1", "x2", "y2")
        if not all(k in zone for k in required_keys):
            return None

        try:
            x1 = float(zone["x1"])
            y1 = float(zone["y1"])
            x2 = float(zone["x2"])
            y2 = float(zone["y2"])
        except (TypeError, ValueError):
            return None

        for val in (x1, y1, x2, y2):
            if math.isnan(val) or math.isinf(val):
                return None

        ref_w, ref_h = self.reference_resolution

        # If coordinates are pixel values (> 1.0), normalize them using reference resolution
        if x1 > 1.0 or x2 > 1.0:
            x1 = x1 / ref_w if ref_w > 0 else x1
            x2 = x2 / ref_w if ref_w > 0 else x2

        if y1 > 1.0 or y2 > 1.0:
            y1 = y1 / ref_h if ref_h > 0 else y1
            y2 = y2 / ref_h if ref_h > 0 else y2

        # Clamp to [0.0, 1.0]
        x1 = max(0.0, min(1.0, x1))
        x2 = max(0.0, min(1.0, x2))
        y1 = max(0.0, min(1.0, y1))
        y2 = max(0.0, min(1.0, y2))

        # Ensure correct ordering
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
        }

    def get_zone_pixels(self, zone, frame_width, frame_height):
        """
        Convert normalized zone coordinates (0.0-1.0) to current frame pixel dimensions.

        Parameters:
            zone (dict): Dict with x1, y1, x2, y2 (normalized floats).
            frame_width (int or float): Current frame width in pixels.
            frame_height (int or float): Current frame height in pixels.

        Returns:
            dict: { "x1": float, "y1": float, "x2": float, "y2": float }
        """
        if frame_width is None or frame_height is None:
            raise ValueError("Frame dimensions must not be None")
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive")

        norm = self._validate_and_normalize_zone(zone)
        if not norm:
            raise ValueError("Invalid zone definition")

        return {
            "x1": norm["x1"] * frame_width,
            "y1": norm["y1"] * frame_height,
            "x2": norm["x2"] * frame_width,
            "y2": norm["y2"] * frame_height,
        }

    def is_inside_zone(self, x, y, zone, frame_width=None, frame_height=None):
        """
        Test whether coordinate point (x, y) lies inside the given zone boundary.
        Supports both resolution-aware pixel coordinates and direct normalized points.
        """
        if x is None or y is None:
            return False

        try:
            px = float(x)
            py = float(y)
        except (TypeError, ValueError):
            return False

        if math.isnan(px) or math.isnan(py) or math.isinf(px) or math.isinf(py):
            return False

        norm_zone = self._validate_and_normalize_zone(zone)
        if not norm_zone:
            return False

        # If frame dimensions are provided, convert zone to frame pixels and evaluate
        if frame_width is not None and frame_height is not None:
            try:
                fw = float(frame_width)
                fh = float(frame_height)
                if fw <= 0 or fh <= 0 or math.isnan(fw) or math.isnan(fh) or math.isinf(fw) or math.isinf(fh):
                    return False
                pixel_zone = self.get_zone_pixels(norm_zone, fw, fh)
                return (
                    pixel_zone["x1"] <= px <= pixel_zone["x2"]
                    and pixel_zone["y1"] <= py <= pixel_zone["y2"]
                )
            except Exception:
                return False

        # If frame dimensions are missing, check if coordinates are already normalized
        if 0.0 <= px <= 1.0 and 0.0 <= py <= 1.0:
            return (
                norm_zone["x1"] <= px <= norm_zone["x2"]
                and norm_zone["y1"] <= py <= norm_zone["y2"]
            )

        # Pixel coordinates without frame dimensions cannot be mapped safely
        return False

    def check_person(self, x, y, frame_width=None, frame_height=None, frame=None):
        """
        Evaluate if a person position (x, y) breaches any registered restricted zone.

        Parameters:
            x (float or int): Horizontal person ground position.
            y (float or int): Vertical person ground position.
            frame_width (int or float, optional): Current frame width in pixels.
            frame_height (int or float, optional): Current frame height in pixels.
            frame (numpy.ndarray, optional): Raw frame image to extract dimensions from.

        Returns:
            dict: {
                "restricted_entry": bool,
                "zone": str or None,
                "message": str
            }
        """
        if frame is not None:
            if hasattr(frame, "shape") and len(frame.shape) >= 2:
                frame_height = frame.shape[0]
                frame_width = frame.shape[1]
            else:
                return {
                    "restricted_entry": False,
                    "zone": None,
                    "message": "Invalid frame passed to restricted-zone check",
                }

        for zone_name, zone in self.zones.items():
            if self.is_inside_zone(x, y, zone, frame_width=frame_width, frame_height=frame_height):
                return {
                    "restricted_entry": True,
                    "zone": zone_name,
                    "message": "Person detected in restricted area",
                }

        return {
            "restricted_entry": False,
            "zone": None,
            "message": "No restricted-zone entry detected",
        }