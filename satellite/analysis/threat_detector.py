"""
Threat detection and analysis algorithms for satellite imagery
"""
import logging
from typing import List, Dict, Any, Tuple
import numpy as np
import cv2
from skimage import feature, filters, morphology, measure
from skimage.util import img_as_ubyte
import rasterio
from rasterio.windows import Window
from scipy import ndimage

logger = logging.getLogger(__name__)


class ThreatDetector:
    """
    Advanced threat detection system for satellite imagery
    Detects explosions, fires, structural damage, and unusual activities
    """
    
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.dataset = None
    
    def __enter__(self):
        self.dataset = rasterio.open(self.image_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.dataset:
            self.dataset.close()
    
    def detect_fires_explosions(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Detect fire and explosion signatures using thermal and spectral analysis
        
        Returns:
            List of detection dictionaries
        """
        detections = []
        
        try:
            # Read RGB bands
            if self.dataset.count >= 3:
                red = self.dataset.read(1)
                green = self.dataset.read(2)
                blue = self.dataset.read(3)
            else:
                logger.warning("Insufficient bands for fire detection")
                return detections
            
            # Normalize bands
            red_norm = self._normalize_band(red)
            green_norm = self._normalize_band(green)
            blue_norm = self._normalize_band(blue)
            
            # Fire detection using red channel dominance and brightness
            fire_index = (red_norm - green_norm) / (red_norm + green_norm + 1e-10)
            brightness = (red_norm + green_norm + blue_norm) / 3
            
            # Create fire mask
            fire_mask = (fire_index > 0.3) & (brightness > 0.5)
            
            # Apply morphological operations to reduce noise
            fire_mask = morphology.opening(fire_mask, morphology.disk(3))
            fire_mask = morphology.closing(fire_mask, morphology.disk(5))
            
            # Label connected components
            labeled_fires = measure.label(fire_mask)
            regions = measure.regionprops(labeled_fires)
            
            for region in regions:
                if region.area > 100:  # Minimum area threshold
                    # Get centroid in pixel coordinates
                    centroid_y, centroid_x = region.centroid
                    
                    # Convert to geographic coordinates
                    lon, lat = self._pixel_to_geo(centroid_x, centroid_y)
                    
                    # Calculate confidence based on fire index and area
                    avg_fire_index = np.mean(fire_index[labeled_fires == region.label])
                    confidence = min(0.6 + (avg_fire_index * 0.4), 0.99)
                    
                    # Determine severity based on area and intensity
                    severity = self._calculate_severity(region.area, avg_fire_index)
                    
                    detections.append({
                        'threat_type': 'fire',
                        'severity': severity,
                        'confidence': float(confidence),
                        'location': (float(lat), float(lon)),
                        'pixel_coords': {'x': int(centroid_x), 'y': int(centroid_y)},
                        'area_pixels': int(region.area),
                        'description': self._generate_fire_description(region.area, severity),
                        'technical_details': {
                            'fire_index': float(avg_fire_index),
                            'brightness': float(np.mean(brightness[labeled_fires == region.label])),
                            'perimeter': int(region.perimeter)
                        }
                    })
            
            logger.info(f"Detected {len(detections)} potential fire/explosion signatures")
        
        except Exception as e:
            logger.error(f"Error in fire detection: {str(e)}")
        
        return detections
    
    def detect_structural_damage(self) -> List[Dict[str, Any]]:
        """
        Detect structural damage using edge detection and texture analysis
        
        Returns:
            List of detection dictionaries
        """
        detections = []
        
        try:
            # Read panchromatic or first band
            image = self.dataset.read(1)
            image_norm = self._normalize_band(image)
            
            # Convert to uint8 for OpenCV
            image_uint8 = img_as_ubyte(image_norm)
            
            # Edge detection
            edges = feature.canny(image_norm, sigma=2)
            
            # Texture analysis using local standard deviation
            texture = ndimage.generic_filter(image_norm, np.std, size=15)
            
            # Identify irregular patterns (potential damage)
            damage_mask = (texture > np.percentile(texture, 85)) & edges
            
            # Morphological operations
            damage_mask = morphology.opening(damage_mask, morphology.disk(2))
            damage_mask = morphology.closing(damage_mask, morphology.disk(4))
            
            # Label regions
            labeled_damage = measure.label(damage_mask)
            regions = measure.regionprops(labeled_damage)
            
            for region in regions:
                if region.area > 200:  # Minimum area for structural damage
                    centroid_y, centroid_x = region.centroid
                    lon, lat = self._pixel_to_geo(centroid_x, centroid_y)
                    
                    # Calculate irregularity score
                    circularity = 4 * np.pi * region.area / (region.perimeter ** 2)
                    irregularity = 1 - circularity
                    
                    confidence = min(0.5 + (irregularity * 0.4), 0.95)
                    severity = 'high' if irregularity > 0.7 else 'medium'
                    
                    detections.append({
                        'threat_type': 'structural_damage',
                        'severity': severity,
                        'confidence': float(confidence),
                        'location': (float(lat), float(lon)),
                        'pixel_coords': {'x': int(centroid_x), 'y': int(centroid_y)},
                        'area_pixels': int(region.area),
                        'description': self._generate_damage_description(region.area, irregularity),
                        'technical_details': {
                            'irregularity_score': float(irregularity),
                            'edge_density': float(np.sum(edges[labeled_damage == region.label]) / region.area),
                            'texture_variance': float(np.var(texture[labeled_damage == region.label]))
                        }
                    })
            
            logger.info(f"Detected {len(detections)} potential structural damage areas")
        
        except Exception as e:
            logger.error(f"Error in structural damage detection: {str(e)}")
        
        return detections
    
    def detect_vehicle_concentrations(self) -> List[Dict[str, Any]]:
        """
        Detect vehicle concentrations and convoys
        
        Returns:
            List of detection dictionaries
        """
        detections = []
        
        try:
            image = self.dataset.read(1)
            image_norm = self._normalize_band(image)
            image_uint8 = img_as_ubyte(image_norm)
            
            # Use blob detection for vehicles
            # Vehicles typically appear as bright spots
            blob_params = cv2.SimpleBlobDetector_Params()
            blob_params.filterByArea = True
            blob_params.minArea = 20
            blob_params.maxArea = 500
            blob_params.filterByCircularity = False
            blob_params.filterByConvexity = False
            
            detector = cv2.SimpleBlobDetector_create(blob_params)
            keypoints = detector.detect(image_uint8)
            
            if len(keypoints) > 5:  # Threshold for concentration
                # Cluster nearby keypoints
                points = np.array([[kp.pt[0], kp.pt[1]] for kp in keypoints])
                
                from scipy.cluster.hierarchy import fclusterdata
                if len(points) > 1:
                    clusters = fclusterdata(points, t=100, criterion='distance')
                    
                    unique_clusters = np.unique(clusters)
                    for cluster_id in unique_clusters:
                        cluster_points = points[clusters == cluster_id]
                        
                        if len(cluster_points) >= 5:  # Minimum vehicles for concern
                            centroid_x = np.mean(cluster_points[:, 0])
                            centroid_y = np.mean(cluster_points[:, 1])
                            
                            lon, lat = self._pixel_to_geo(centroid_x, centroid_y)
                            
                            vehicle_count = len(cluster_points)
                            confidence = min(0.6 + (vehicle_count / 50), 0.9)
                            severity = self._vehicle_severity(vehicle_count)
                            
                            detections.append({
                                'threat_type': 'vehicle_convoy',
                                'severity': severity,
                                'confidence': float(confidence),
                                'location': (float(lat), float(lon)),
                                'pixel_coords': {'x': int(centroid_x), 'y': int(centroid_y)},
                                'vehicle_count': int(vehicle_count),
                                'description': self._generate_vehicle_description(vehicle_count),
                                'technical_details': {
                                    'cluster_spread': float(np.std(cluster_points)),
                                    'formation_type': 'concentrated' if np.std(cluster_points) < 50 else 'dispersed'
                                }
                            })
            
            logger.info(f"Detected {len(detections)} vehicle concentrations")
        
        except Exception as e:
            logger.error(f"Error in vehicle detection: {str(e)}")
        
        return detections
    
    def _normalize_band(self, band: np.ndarray) -> np.ndarray:
        """Normalize band to 0-1 range using percentile stretch"""
        p2, p98 = np.percentile(band[band != 0], (2, 98))
        return np.clip((band - p2) / (p98 - p2), 0, 1)
    
    def _pixel_to_geo(self, x: float, y: float) -> Tuple[float, float]:
        """Convert pixel coordinates to geographic coordinates"""
        lon, lat = self.dataset.xy(y, x)
        return lon, lat
    
    def _calculate_severity(self, area: int, intensity: float) -> str:
        """Calculate severity based on area and intensity"""
        score = (area / 1000) + intensity
        if score > 2.0:
            return 'critical'
        elif score > 1.0:
            return 'high'
        elif score > 0.5:
            return 'medium'
        return 'low'
    
    def _vehicle_severity(self, count: int) -> str:
        """Determine severity based on vehicle count"""
        if count > 20:
            return 'critical'
        elif count > 10:
            return 'high'
        elif count > 5:
            return 'medium'
        return 'low'
    
    def _generate_fire_description(self, area: int, severity: str) -> str:
        """Generate human-readable fire description"""
        area_km2 = area * (self.dataset.res[0] ** 2) / 1_000_000
        
        descriptions = {
            'critical': f'Large-scale fire detected covering approximately {area_km2:.2f} km². Immediate response recommended.',
            'high': f'Significant fire activity detected over {area_km2:.2f} km². Active monitoring advised.',
            'medium': f'Fire signature detected covering {area_km2:.2f} km². Investigation recommended.',
            'low': f'Minor fire activity or hot spot detected over {area_km2:.2f} km².'
        }
        return descriptions.get(severity, 'Fire activity detected.')
    
    def _generate_damage_description(self, area: int, irregularity: float) -> str:
        """Generate human-readable damage description"""
        area_m2 = area * (self.dataset.res[0] ** 2)
        
        if irregularity > 0.8:
            return f'Severe structural damage detected covering approximately {area_m2:.0f} m². Pattern indicates potential explosive impact.'
        elif irregularity > 0.6:
            return f'Moderate structural damage observed over {area_m2:.0f} m². Possible building collapse or significant damage.'
        return f'Structural anomaly detected covering {area_m2:.0f} m². Further analysis recommended.'
    
    def _generate_vehicle_description(self, count: int) -> str:
        """Generate human-readable vehicle concentration description"""
        if count > 20:
            return f'Large convoy or military formation detected with {count}+ vehicles. High-priority monitoring recommended.'
        elif count > 10:
            return f'Significant vehicle concentration identified with approximately {count} vehicles. Could indicate convoy movement.'
        elif count > 5:
            return f'Vehicle grouping detected with {count} vehicles. May indicate coordinated movement.'
        return f'Small vehicle cluster identified with {count} vehicles.'