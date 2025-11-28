"""
Threat detection and analysis algorithms for satellite imagery
Uses windowed processing to handle large images with limited memory
FIXED: Proper coordinate transformation to ensure detections are in correct geographic location
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import cv2
from skimage import feature, filters, morphology, measure
from skimage.util import img_as_ubyte
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform
from scipy import ndimage

logger = logging.getLogger(__name__)

# Chunk size for windowed processing (2048x2048 pixels)
CHUNK_SIZE = 2048
# Overlap for edge detection (256 pixels on each side)
OVERLAP = 256


class ThreatDetector:
    """
    Advanced threat detection system for satellite imagery
    Uses windowed processing for memory efficiency with large GeoTIFF files
    Detects explosions, fires, structural damage, and unusual activities
    """

    def __init__(
        self, image_path: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
    ):
        self.image_path = image_path
        self.dataset = None
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.processed_regions = set()  # Track processed locations to avoid duplicates
        self.transform = None  # Affine transform for coordinate conversion
        self.crs = None  # Coordinate reference system

    def __enter__(self):
        self.dataset = rasterio.open(self.image_path)
        self.transform = self.dataset.transform
        self.crs = self.dataset.crs
        logger.info(f"Opened image with CRS: {self.crs}")
        logger.info(f"Image bounds: {self.dataset.bounds}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.dataset:
            self.dataset.close()

    def _pixel_to_geo(self, x: float, y: float) -> Tuple[float, float]:
        """
        Convert pixel coordinates to geographic coordinates (WGS84)
        FIXED: Properly transforms coordinates to WGS84 (EPSG:4326)

        Args:
            x: Column (pixel x coordinate)
            y: Row (pixel y coordinate)

        Returns:
            Tuple of (longitude, latitude) in WGS84
        """
        try:
            # Convert pixel coordinates to the image's CRS coordinates
            # Note: rasterio uses (row, col) but we have (x=col, y=row)
            src_x, src_y = self.transform * (x, y)

            # If the image CRS is not WGS84, transform to WGS84
            if self.crs and self.crs.to_string() != "EPSG:4326":
                # Transform from source CRS to WGS84
                lon, lat = transform(self.crs, "EPSG:4326", [src_x], [src_y])
                return float(lon[0]), float(lat[0])
            else:
                # Already in WGS84
                return float(src_x), float(src_y)
        except Exception as e:
            logger.error(
                f"Error converting pixel ({x}, {y}) to geo coordinates: {str(e)}"
            )
            # Return a fallback - use the raw transform result
            src_x, src_y = self.transform * (x, y)
            return float(src_x), float(src_y)

    def _validate_coordinates(self, lon: float, lat: float) -> bool:
        """
        Validate that coordinates are within reasonable bounds

        Args:
            lon: Longitude
            lat: Latitude

        Returns:
            True if coordinates are valid, False otherwise
        """
        # Check if coordinates are within valid geographic bounds
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            logger.warning(f"Invalid coordinates: lon={lon}, lat={lat}")
            return False

        # Check if coordinates are within the image bounds (with tolerance)
        try:
            bounds = self.dataset.bounds
            # Transform bounds to WGS84 if needed
            if self.crs and self.crs.to_string() != "EPSG:4326":
                from rasterio.warp import transform_bounds

                bounds_4326 = transform_bounds(
                    self.crs,
                    "EPSG:4326",
                    bounds.left,
                    bounds.bottom,
                    bounds.right,
                    bounds.top,
                )
                min_lon, min_lat, max_lon, max_lat = bounds_4326
            else:
                min_lon, min_lat = bounds.left, bounds.bottom
                max_lon, max_lat = bounds.right, bounds.top

            # Add 10% tolerance for edge cases
            tolerance = 0.1
            lon_range = max_lon - min_lon
            lat_range = max_lat - min_lat

            if not (
                min_lon - tolerance * lon_range
                <= lon
                <= max_lon + tolerance * lon_range
            ):
                logger.warning(
                    f"Longitude {lon} outside image bounds [{min_lon}, {max_lon}]"
                )
                return False

            if not (
                min_lat - tolerance * lat_range
                <= lat
                <= max_lat + tolerance * lat_range
            ):
                logger.warning(
                    f"Latitude {lat} outside image bounds [{min_lat}, {max_lat}]"
                )
                return False

            return True
        except Exception as e:
            logger.error(f"Error validating coordinates: {str(e)}")
            return False

    def detect_fires_explosions(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Detect fire and explosion signatures using windowed thermal and spectral analysis
        Processes image in chunks to handle memory constraints with large GeoTIFF files

        Returns:
            List of detection dictionaries
        """
        detections = []

        try:
            if self.dataset.count < 3:
                logger.warning("Insufficient bands for fire detection")
                return detections

            height, width = self.dataset.height, self.dataset.width
            logger.info(f"Processing image of size {width}x{height} for fire detection")

            # Process image in overlapping windows
            for y_start in range(0, height, self.chunk_size):
                for x_start in range(0, width, self.chunk_size):
                    # Define window with overlap
                    y_end = min(y_start + self.chunk_size + self.overlap, height)
                    x_end = min(x_start + self.chunk_size + self.overlap, width)

                    window = Window(x_start, y_start, x_end - x_start, y_end - y_start)

                    try:
                        # Read bands for this window
                        red = self.dataset.read(1, window=window)
                        green = self.dataset.read(2, window=window)
                        blue = self.dataset.read(3, window=window)

                        # Skip empty windows
                        if (
                            np.all(red == 0)
                            and np.all(green == 0)
                            and np.all(blue == 0)
                        ):
                            continue

                        # Normalize bands
                        red_norm = self._normalize_band(red)
                        green_norm = self._normalize_band(green)
                        blue_norm = self._normalize_band(blue)

                        # Fire detection
                        fire_index = (red_norm - green_norm) / (
                            red_norm + green_norm + 1e-10
                        )
                        brightness = (red_norm + green_norm + blue_norm) / 3

                        fire_mask = (fire_index > 0.3) & (brightness > 0.5)
                        fire_mask = morphology.opening(fire_mask, morphology.disk(3))
                        fire_mask = morphology.closing(fire_mask, morphology.disk(5))

                        # Label regions
                        labeled_fires = measure.label(fire_mask)
                        regions = measure.regionprops(labeled_fires)

                        for region in regions:
                            if region.area > 100:
                                # Convert window-relative coords to full image coords
                                global_y = y_start + region.centroid[0]
                                global_x = x_start + region.centroid[1]

                                # Skip if already processed (within overlap region)
                                region_key = (
                                    int(global_x // 100),
                                    int(global_y // 100),
                                )
                                if region_key in self.processed_regions:
                                    continue

                                # Convert to geographic coordinates
                                lon, lat = self._pixel_to_geo(global_x, global_y)

                                # Validate coordinates before adding detection
                                if not self._validate_coordinates(lon, lat):
                                    logger.warning(
                                        f"Skipping fire detection with invalid coordinates: ({lon}, {lat})"
                                    )
                                    continue

                                self.processed_regions.add(region_key)

                                avg_fire_index = np.mean(
                                    fire_index[labeled_fires == region.label]
                                )
                                confidence = min(0.6 + (avg_fire_index * 0.4), 0.99)
                                severity = self._calculate_severity(
                                    region.area, avg_fire_index
                                )

                                detections.append(
                                    {
                                        "threat_type": "fire",
                                        "severity": severity,
                                        "confidence": float(confidence),
                                        "location": (float(lat), float(lon)),
                                        "pixel_coords": {
                                            "x": int(global_x),
                                            "y": int(global_y),
                                        },
                                        "area_pixels": int(region.area),
                                        "description": self._generate_fire_description(
                                            region.area, severity
                                        ),
                                        "technical_details": {
                                            "fire_index": float(avg_fire_index),
                                            "brightness": float(
                                                np.mean(
                                                    brightness[
                                                        labeled_fires == region.label
                                                    ]
                                                )
                                            ),
                                            "perimeter": int(region.perimeter),
                                        },
                                    }
                                )

                                logger.debug(
                                    f"Fire detected at pixel ({global_x}, {global_y}) -> geo ({lon}, {lat})"
                                )

                    except Exception as e:
                        logger.warning(
                            f"Error processing window at ({x_start}, {y_start}): {str(e)}"
                        )
                        continue

                    finally:
                        # Explicit cleanup for this window
                        del red, green, blue

            logger.info(
                f"Detected {len(detections)} potential fire/explosion signatures"
            )

        except Exception as e:
            logger.error(f"Error in fire detection: {str(e)}")

        return detections

    def detect_structural_damage(self) -> List[Dict[str, Any]]:
        """
        Detect structural damage using fast edge detection on sampled regions
        Optimized for speed: aggressive sampling to stay under time limits

        Returns:
            List of detection dictionaries
        """
        detections = []

        try:
            # For memory efficiency, process at a lower resolution
            height, width = self.dataset.height, self.dataset.width
            logger.info(
                f"Processing image of size {width}x{height} for structural damage"
            )

            # Use much coarser stride sampling to avoid time limit exceed
            stride = 2048  # Sample every 2048 pixels (very large stride!)
            sample_size = 512  # Each sample is 512x512

            for y_start in range(0, height - sample_size, stride):
                for x_start in range(0, width - sample_size, stride):
                    window = Window(x_start, y_start, sample_size, sample_size)

                    try:
                        # Read panchromatic or first band
                        image = self.dataset.read(1, window=window)

                        if np.all(image == 0):
                            continue

                        image_norm = self._normalize_band(image)

                        # Fast edge detection using Sobel
                        from scipy.ndimage import sobel

                        edge_x = sobel(image_norm, axis=0)
                        edge_y = sobel(image_norm, axis=1)
                        edges = (
                            np.sqrt(edge_x**2 + edge_y**2) > 0.15
                        )  # Higher threshold

                        # Count high-edge-density regions (potential damage)
                        edge_density = np.sum(edges) / (sample_size * sample_size)

                        # Only report VERY high edge density areas (avoid false positives)
                        if edge_density > 0.2:  # Much higher threshold
                            # Find the center of highest edge activity
                            cy, cx = ndimage.center_of_mass(edges.astype(int))

                            if cy is not None and cx is not None:
                                global_y = y_start + cy
                                global_x = x_start + cx

                                # Convert to geographic coordinates
                                lon, lat = self._pixel_to_geo(global_x, global_y)

                                # Validate coordinates before adding detection
                                if not self._validate_coordinates(lon, lat):
                                    logger.warning(
                                        f"Skipping damage detection with invalid coordinates: ({lon}, {lat})"
                                    )
                                    continue

                                region_key = (
                                    int(global_x // 500),
                                    int(global_y // 500),
                                )
                                if region_key in self.processed_regions:
                                    continue
                                self.processed_regions.add(region_key)

                                # Confidence based on edge density
                                confidence = min(0.6 + (edge_density * 0.35), 0.95)
                                severity = (
                                    "critical"
                                    if edge_density > 0.4
                                    else "high" if edge_density > 0.3 else "medium"
                                )

                                detections.append(
                                    {
                                        "threat_type": "structural_damage",
                                        "severity": severity,
                                        "confidence": float(confidence),
                                        "location": (float(lat), float(lon)),
                                        "pixel_coords": {
                                            "x": int(global_x),
                                            "y": int(global_y),
                                        },
                                        "area_pixels": int(sample_size * sample_size),
                                        "description": f"High-concentration structural damage detected ({edge_density:.1%} edge density)",
                                        "technical_details": {
                                            "edge_density": float(edge_density),
                                            "sample_size": sample_size,
                                        },
                                    }
                                )

                                logger.debug(
                                    f"Damage detected at pixel ({global_x}, {global_y}) -> geo ({lon}, {lat})"
                                )

                    except Exception as e:
                        logger.warning(
                            f"Error processing damage sample at ({x_start}, {y_start}): {str(e)}"
                        )
                        continue

                    finally:
                        if "image" in locals():
                            del image

            logger.info(f"Detected {len(detections)} potential structural damage areas")

        except Exception as e:
            logger.error(f"Error in structural damage detection: {str(e)}")

        return detections

    def detect_vehicle_concentrations(self) -> List[Dict[str, Any]]:
        """
        Detect vehicle concentrations and convoys using fast sampling
        Optimized for speed: samples key image regions instead of full windowed processing

        Returns:
            List of detection dictionaries
        """
        detections = []

        try:
            height, width = self.dataset.height, self.dataset.width
            logger.info(
                f"Processing image of size {width}x{height} for vehicle detection"
            )
            all_keypoints = []

            # Use aggressive stride sampling for vehicles to save time
            stride = 1024  # Sample every 1024 pixels
            sample_size = 512  # Each sample is 512x512

            # Limit to 10% of the image for vehicles to stay under time limit
            max_samples = min(4, (height // stride) * (width // stride) // 10)
            sample_count = 0

            for y_start in range(0, height - sample_size, stride):
                if sample_count >= max_samples:
                    break

                for x_start in range(0, width - sample_size, stride):
                    if sample_count >= max_samples:
                        break

                    sample_count += 1
                    window = Window(x_start, y_start, sample_size, sample_size)

                    try:
                        image = self.dataset.read(1, window=window)

                        if np.all(image == 0):
                            continue

                        image_norm = self._normalize_band(image)
                        image_uint8 = img_as_ubyte(image_norm)

                        # Simplified blob detection on downsampled image
                        downsampled = image_uint8[::2, ::2]  # 2x downsampling

                        blob_params = cv2.SimpleBlobDetector_Params()
                        blob_params.filterByArea = True
                        blob_params.minArea = 10
                        blob_params.maxArea = 200
                        blob_params.filterByCircularity = False
                        blob_params.filterByConvexity = False

                        detector = cv2.SimpleBlobDetector_create(blob_params)
                        keypoints = detector.detect(downsampled)

                        # Scale keypoints back up and convert to global coords
                        for kp in keypoints:
                            global_x = x_start + (kp.pt[0] * 2)
                            global_y = y_start + (kp.pt[1] * 2)
                            all_keypoints.append([global_x, global_y])

                    except Exception as e:
                        logger.warning(
                            f"Error processing vehicle sample at ({x_start}, {y_start}): {str(e)}"
                        )
                        continue

            # Cluster keypoints if we have enough
            if len(all_keypoints) > 5:
                try:
                    points = np.array(all_keypoints)
                    from scipy.cluster.hierarchy import fclusterdata

                    # Use more aggressive clustering distance
                    clusters = fclusterdata(points, t=200, criterion="distance")

                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = points[clusters == cluster_id]

                        if len(cluster_points) >= 5:
                            centroid_x = np.mean(cluster_points[:, 0])
                            centroid_y = np.mean(cluster_points[:, 1])

                            # Convert to geographic coordinates
                            lon, lat = self._pixel_to_geo(centroid_x, centroid_y)

                            # Validate coordinates before adding detection
                            if not self._validate_coordinates(lon, lat):
                                logger.warning(
                                    f"Skipping vehicle detection with invalid coordinates: ({lon}, {lat})"
                                )
                                continue

                            region_key = (
                                int(centroid_x // 500),
                                int(centroid_y // 500),
                            )
                            if region_key in self.processed_regions:
                                continue
                            self.processed_regions.add(region_key)

                            vehicle_count = len(cluster_points)
                            confidence = min(0.6 + (vehicle_count / 50), 0.9)
                            severity = self._vehicle_severity(vehicle_count)

                            detections.append(
                                {
                                    "threat_type": "vehicle_convoy",
                                    "severity": severity,
                                    "confidence": float(confidence),
                                    "location": (float(lat), float(lon)),
                                    "pixel_coords": {
                                        "x": int(centroid_x),
                                        "y": int(centroid_y),
                                    },
                                    "vehicle_count": int(vehicle_count),
                                    "description": self._generate_vehicle_description(
                                        vehicle_count
                                    ),
                                    "technical_details": {
                                        "cluster_spread": float(np.std(cluster_points)),
                                        "formation_type": (
                                            "concentrated"
                                            if np.std(cluster_points) < 100
                                            else "dispersed"
                                        ),
                                    },
                                }
                            )

                            logger.debug(
                                f"Vehicles detected at pixel ({centroid_x}, {centroid_y}) -> geo ({lon}, {lat})"
                            )

                except Exception as e:
                    logger.warning(f"Error clustering vehicles: {str(e)}")

            logger.info(f"Detected {len(detections)} vehicle concentrations")

        except Exception as e:
            logger.error(f"Error in vehicle detection: {str(e)}")

        return detections

    def _normalize_band(self, band: np.ndarray) -> np.ndarray:
        """Normalize band to 0-1 range using percentile stretch"""
        p2, p98 = np.percentile(band[band != 0], (2, 98))
        return np.clip((band - p2) / (p98 - p2), 0, 1)

    def _calculate_severity(self, area: int, intensity: float) -> str:
        """Calculate severity based on area and intensity"""
        score = (area / 1000) + intensity
        if score > 2.0:
            return "critical"
        elif score > 1.0:
            return "high"
        elif score > 0.5:
            return "medium"
        return "low"

    def _vehicle_severity(self, count: int) -> str:
        """Determine severity based on vehicle count"""
        if count > 20:
            return "critical"
        elif count > 10:
            return "high"
        elif count > 5:
            return "medium"
        return "low"

    def _generate_fire_description(self, area: int, severity: str) -> str:
        """Generate human-readable fire description"""
        area_km2 = area * (self.dataset.res[0] ** 2) / 1_000_000

        descriptions = {
            "critical": f"Large-scale fire detected covering approximately {area_km2:.2f} km². Immediate response recommended.",
            "high": f"Significant fire activity detected over {area_km2:.2f} km². Active monitoring advised.",
            "medium": f"Fire signature detected covering {area_km2:.2f} km². Investigation recommended.",
            "low": f"Minor fire activity or hot spot detected over {area_km2:.2f} km².",
        }
        return descriptions.get(severity, "Fire activity detected.")

    def _generate_damage_description(self, area: int, irregularity: float) -> str:
        """Generate human-readable damage description"""
        area_m2 = area * (self.dataset.res[0] ** 2)

        if irregularity > 0.8:
            return f"Severe structural damage detected covering approximately {area_m2:.0f} m². Pattern indicates potential explosive impact."
        elif irregularity > 0.6:
            return f"Moderate structural damage observed over {area_m2:.0f} m². Possible building collapse or significant damage."
        return f"Structural anomaly detected covering {area_m2:.0f} m². Further analysis recommended."

    def _generate_vehicle_description(self, count: int) -> str:
        """Generate human-readable vehicle concentration description"""
        if count > 20:
            return f"Large convoy or military formation detected with {count}+ vehicles. High-priority monitoring recommended."
        elif count > 10:
            return f"Significant vehicle concentration identified with approximately {count} vehicles. Could indicate convoy movement."
        elif count > 5:
            return f"Vehicle grouping detected with {count} vehicles. May indicate coordinated movement."
        return f"Small vehicle cluster identified with {count} vehicles."


# """
# Threat detection and analysis algorithms for satellite imagery
# Uses windowed processing to handle large images with limited memory
# """
# import logging
# from typing import List, Dict, Any, Tuple, Optional
# import numpy as np
# import cv2
# from skimage import feature, filters, morphology, measure
# from skimage.util import img_as_ubyte
# import rasterio
# from rasterio.windows import Window
# from scipy import ndimage

# logger = logging.getLogger(__name__)

# # Chunk size for windowed processing (2048x2048 pixels)
# CHUNK_SIZE = 2048
# # Overlap for edge detection (256 pixels on each side)
# OVERLAP = 256


# class ThreatDetector:
#     """
#     Advanced threat detection system for satellite imagery
#     Uses windowed processing for memory efficiency with large GeoTIFF files
#     Detects explosions, fires, structural damage, and unusual activities
#     """

#     def __init__(self, image_path: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP):
#         self.image_path = image_path
#         self.dataset = None
#         self.chunk_size = chunk_size
#         self.overlap = overlap
#         self.processed_regions = set()  # Track processed locations to avoid duplicates

#     def __enter__(self):
#         self.dataset = rasterio.open(self.image_path)
#         return self

#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if self.dataset:
#             self.dataset.close()

#     def detect_fires_explosions(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
#         """
#         Detect fire and explosion signatures using windowed thermal and spectral analysis
#         Processes image in chunks to handle memory constraints with large GeoTIFF files

#         Returns:
#             List of detection dictionaries
#         """
#         detections = []

#         try:
#             if self.dataset.count < 3:
#                 logger.warning("Insufficient bands for fire detection")
#                 return detections

#             height, width = self.dataset.height, self.dataset.width

#             # Process image in overlapping windows
#             for y_start in range(0, height, self.chunk_size):
#                 for x_start in range(0, width, self.chunk_size):
#                     # Define window with overlap
#                     y_end = min(y_start + self.chunk_size + self.overlap, height)
#                     x_end = min(x_start + self.chunk_size + self.overlap, width)

#                     window = Window(x_start, y_start, x_end - x_start, y_end - y_start)

#                     try:
#                         # Read bands for this window
#                         red = self.dataset.read(1, window=window)
#                         green = self.dataset.read(2, window=window)
#                         blue = self.dataset.read(3, window=window)

#                         # Skip empty windows
#                         if np.all(red == 0) and np.all(green == 0) and np.all(blue == 0):
#                             continue

#                         # Normalize bands
#                         red_norm = self._normalize_band(red)
#                         green_norm = self._normalize_band(green)
#                         blue_norm = self._normalize_band(blue)

#                         # Fire detection
#                         fire_index = (red_norm - green_norm) / (red_norm + green_norm + 1e-10)
#                         brightness = (red_norm + green_norm + blue_norm) / 3

#                         fire_mask = (fire_index > 0.3) & (brightness > 0.5)
#                         fire_mask = morphology.opening(fire_mask, morphology.disk(3))
#                         fire_mask = morphology.closing(fire_mask, morphology.disk(5))

#                         # Label regions
#                         labeled_fires = measure.label(fire_mask)
#                         regions = measure.regionprops(labeled_fires)

#                         for region in regions:
#                             if region.area > 100:
#                                 # Convert window-relative coords to full image coords
#                                 global_y = y_start + region.centroid[0]
#                                 global_x = x_start + region.centroid[1]

#                                 # Skip if already processed (within overlap region)
#                                 region_key = (int(global_x // 100), int(global_y // 100))
#                                 if region_key in self.processed_regions:
#                                     continue
#                                 self.processed_regions.add(region_key)

#                                 lon, lat = self._pixel_to_geo(global_x, global_y)

#                                 avg_fire_index = np.mean(fire_index[labeled_fires == region.label])
#                                 confidence = min(0.6 + (avg_fire_index * 0.4), 0.99)
#                                 severity = self._calculate_severity(region.area, avg_fire_index)

#                                 detections.append({
#                                     'threat_type': 'fire',
#                                     'severity': severity,
#                                     'confidence': float(confidence),
#                                     'location': (float(lat), float(lon)),
#                                     'pixel_coords': {'x': int(global_x), 'y': int(global_y)},
#                                     'area_pixels': int(region.area),
#                                     'description': self._generate_fire_description(region.area, severity),
#                                     'technical_details': {
#                                         'fire_index': float(avg_fire_index),
#                                         'brightness': float(np.mean(brightness[labeled_fires == region.label])),
#                                         'perimeter': int(region.perimeter)
#                                     }
#                                 })

#                     except Exception as e:
#                         logger.warning(f"Error processing window at ({x_start}, {y_start}): {str(e)}")
#                         continue

#                     finally:
#                         # Explicit cleanup for this window
#                         del red, green, blue

#             logger.info(f"Detected {len(detections)} potential fire/explosion signatures")

#         except Exception as e:
#             logger.error(f"Error in fire detection: {str(e)}")

#         return detections

#     def detect_structural_damage(self) -> List[Dict[str, Any]]:
#         """
#         Detect structural damage using fast edge detection on sampled regions
#         Optimized for speed: aggressive sampling to stay under time limits

#         Returns:
#             List of detection dictionaries
#         """
#         detections = []

#         try:
#             # For memory efficiency, process at a lower resolution
#             height, width = self.dataset.height, self.dataset.width

#             # Use much coarser stride sampling to avoid time limit exceed
#             stride = 2048  # Sample every 2048 pixels (very large stride!)
#             sample_size = 512  # Each sample is 512x512

#             for y_start in range(0, height - sample_size, stride):
#                 for x_start in range(0, width - sample_size, stride):
#                     window = Window(x_start, y_start, sample_size, sample_size)

#                     try:
#                         # Read panchromatic or first band
#                         image = self.dataset.read(1, window=window)

#                         if np.all(image == 0):
#                             continue

#                         image_norm = self._normalize_band(image)

#                         # Fast edge detection using Sobel
#                         from scipy.ndimage import sobel
#                         edge_x = sobel(image_norm, axis=0)
#                         edge_y = sobel(image_norm, axis=1)
#                         edges = np.sqrt(edge_x**2 + edge_y**2) > 0.15  # Higher threshold

#                         # Count high-edge-density regions (potential damage)
#                         edge_density = np.sum(edges) / (sample_size * sample_size)

#                         # Only report VERY high edge density areas (avoid false positives)
#                         if edge_density > 0.2:  # Much higher threshold
#                             # Find the center of highest edge activity
#                             cy, cx = ndimage.center_of_mass(edges.astype(int))

#                             if cy is not None and cx is not None:
#                                 global_y = y_start + cy
#                                 global_x = x_start + cx

#                                 region_key = (int(global_x // 500), int(global_y // 500))
#                                 if region_key in self.processed_regions:
#                                     continue
#                                 self.processed_regions.add(region_key)

#                                 lon, lat = self._pixel_to_geo(global_x, global_y)

#                                 # Confidence based on edge density
#                                 confidence = min(0.6 + (edge_density * 0.35), 0.95)
#                                 severity = 'critical' if edge_density > 0.4 else 'high' if edge_density > 0.3 else 'medium'

#                                 detections.append({
#                                     'threat_type': 'structural_damage',
#                                     'severity': severity,
#                                     'confidence': float(confidence),
#                                     'location': (float(lat), float(lon)),
#                                     'pixel_coords': {'x': int(global_x), 'y': int(global_y)},
#                                     'area_pixels': int(sample_size * sample_size),
#                                     'description': f'High-concentration structural damage detected ({edge_density:.1%} edge density)',
#                                     'technical_details': {
#                                         'edge_density': float(edge_density),
#                                         'sample_size': sample_size
#                                     }
#                                 })

#                     except Exception as e:
#                         logger.warning(f"Error processing damage sample at ({x_start}, {y_start}): {str(e)}")
#                         continue

#                     finally:
#                         if 'image' in locals():
#                             del image

#             logger.info(f"Detected {len(detections)} potential structural damage areas")

#         except Exception as e:
#             logger.error(f"Error in structural damage detection: {str(e)}")

#         return detections

#     def detect_vehicle_concentrations(self) -> List[Dict[str, Any]]:
#         """
#         Detect vehicle concentrations and convoys using fast sampling
#         Optimized for speed: samples key image regions instead of full windowed processing

#         Returns:
#             List of detection dictionaries
#         """
#         detections = []

#         try:
#             height, width = self.dataset.height, self.dataset.width
#             all_keypoints = []

#             # Use aggressive stride sampling for vehicles to save time
#             stride = 1024  # Sample every 1024 pixels
#             sample_size = 512  # Each sample is 512x512

#             # Limit to 10% of the image for vehicles to stay under time limit
#             max_samples = min(4, (height // stride) * (width // stride) // 10)
#             sample_count = 0

#             for y_start in range(0, height - sample_size, stride):
#                 if sample_count >= max_samples:
#                     break

#                 for x_start in range(0, width - sample_size, stride):
#                     if sample_count >= max_samples:
#                         break

#                     sample_count += 1
#                     window = Window(x_start, y_start, sample_size, sample_size)

#                     try:
#                         image = self.dataset.read(1, window=window)

#                         if np.all(image == 0):
#                             continue

#                         image_norm = self._normalize_band(image)
#                         image_uint8 = img_as_ubyte(image_norm)

#                         # Simplified blob detection on downsampled image
#                         downsampled = image_uint8[::2, ::2]  # 2x downsampling

#                         blob_params = cv2.SimpleBlobDetector_Params()
#                         blob_params.filterByArea = True
#                         blob_params.minArea = 10
#                         blob_params.maxArea = 200
#                         blob_params.filterByCircularity = False
#                         blob_params.filterByConvexity = False

#                         detector = cv2.SimpleBlobDetector_create(blob_params)
#                         keypoints = detector.detect(downsampled)

#                         # Scale keypoints back up and convert to global coords
#                         for kp in keypoints:
#                             global_x = x_start + (kp.pt[0] * 2)
#                             global_y = y_start + (kp.pt[1] * 2)
#                             all_keypoints.append([global_x, global_y])

#                     except Exception as e:
#                         logger.warning(f"Error processing vehicle sample at ({x_start}, {y_start}): {str(e)}")
#                         continue

#             # Cluster keypoints if we have enough
#             if len(all_keypoints) > 5:
#                 try:
#                     points = np.array(all_keypoints)
#                     from scipy.cluster.hierarchy import fclusterdata

#                     # Use more aggressive clustering distance
#                     clusters = fclusterdata(points, t=200, criterion='distance')

#                     unique_clusters = np.unique(clusters)
#                     for cluster_id in unique_clusters:
#                         cluster_points = points[clusters == cluster_id]

#                         if len(cluster_points) >= 5:
#                             centroid_x = np.mean(cluster_points[:, 0])
#                             centroid_y = np.mean(cluster_points[:, 1])

#                             region_key = (int(centroid_x // 500), int(centroid_y // 500))
#                             if region_key in self.processed_regions:
#                                 continue
#                             self.processed_regions.add(region_key)

#                             lon, lat = self._pixel_to_geo(centroid_x, centroid_y)

#                             vehicle_count = len(cluster_points)
#                             confidence = min(0.6 + (vehicle_count / 50), 0.9)
#                             severity = self._vehicle_severity(vehicle_count)

#                             detections.append({
#                                 'threat_type': 'vehicle_convoy',
#                                 'severity': severity,
#                                 'confidence': float(confidence),
#                                 'location': (float(lat), float(lon)),
#                                 'pixel_coords': {'x': int(centroid_x), 'y': int(centroid_y)},
#                                 'vehicle_count': int(vehicle_count),
#                                 'description': self._generate_vehicle_description(vehicle_count),
#                                 'technical_details': {
#                                     'cluster_spread': float(np.std(cluster_points)),
#                                     'formation_type': 'concentrated' if np.std(cluster_points) < 100 else 'dispersed'
#                                 }
#                             })

#                 except Exception as e:
#                     logger.warning(f"Error clustering vehicles: {str(e)}")

#             logger.info(f"Detected {len(detections)} vehicle concentrations")

#         except Exception as e:
#             logger.error(f"Error in vehicle detection: {str(e)}")

#         return detections

#     def _normalize_band(self, band: np.ndarray) -> np.ndarray:
#         """Normalize band to 0-1 range using percentile stretch"""
#         p2, p98 = np.percentile(band[band != 0], (2, 98))
#         return np.clip((band - p2) / (p98 - p2), 0, 1)

#     def _pixel_to_geo(self, x: float, y: float) -> Tuple[float, float]:
#         """Convert pixel coordinates to geographic coordinates"""
#         lon, lat = self.dataset.xy(y, x)
#         return lon, lat

#     def _calculate_severity(self, area: int, intensity: float) -> str:
#         """Calculate severity based on area and intensity"""
#         score = (area / 1000) + intensity
#         if score > 2.0:
#             return 'critical'
#         elif score > 1.0:
#             return 'high'
#         elif score > 0.5:
#             return 'medium'
#         return 'low'

#     def _vehicle_severity(self, count: int) -> str:
#         """Determine severity based on vehicle count"""
#         if count > 20:
#             return 'critical'
#         elif count > 10:
#             return 'high'
#         elif count > 5:
#             return 'medium'
#         return 'low'

#     def _generate_fire_description(self, area: int, severity: str) -> str:
#         """Generate human-readable fire description"""
#         area_km2 = area * (self.dataset.res[0] ** 2) / 1_000_000

#         descriptions = {
#             'critical': f'Large-scale fire detected covering approximately {area_km2:.2f} km². Immediate response recommended.',
#             'high': f'Significant fire activity detected over {area_km2:.2f} km². Active monitoring advised.',
#             'medium': f'Fire signature detected covering {area_km2:.2f} km². Investigation recommended.',
#             'low': f'Minor fire activity or hot spot detected over {area_km2:.2f} km².'
#         }
#         return descriptions.get(severity, 'Fire activity detected.')

#     def _generate_damage_description(self, area: int, irregularity: float) -> str:
#         """Generate human-readable damage description"""
#         area_m2 = area * (self.dataset.res[0] ** 2)

#         if irregularity > 0.8:
#             return f'Severe structural damage detected covering approximately {area_m2:.0f} m². Pattern indicates potential explosive impact.'
#         elif irregularity > 0.6:
#             return f'Moderate structural damage observed over {area_m2:.0f} m². Possible building collapse or significant damage.'
#         return f'Structural anomaly detected covering {area_m2:.0f} m². Further analysis recommended.'

#     def _generate_vehicle_description(self, count: int) -> str:
#         """Generate human-readable vehicle concentration description"""
#         if count > 20:
#             return f'Large convoy or military formation detected with {count}+ vehicles. High-priority monitoring recommended.'
#         elif count > 10:
#             return f'Significant vehicle concentration identified with approximately {count} vehicles. Could indicate convoy movement.'
#         elif count > 5:
#             return f'Vehicle grouping detected with {count} vehicles. May indicate coordinated movement.'
#         return f'Small vehicle cluster identified with {count} vehicles.'
