"""
Main analysis processor coordinating threat detection algorithms
"""

import logging
from typing import Dict, Any, List
from django.utils import timezone
from django.contrib.gis.geos import Point

logger = logging.getLogger(__name__)


class AnalysisProcessor:
    """
    Main processor for coordinating satellite image analysis
    """

    def __init__(self, analysis_result_instance):
        self.analysis = analysis_result_instance
        self.satellite_image = analysis_result_instance.satellite_image
        self.image_path = self.satellite_image.optimized_image.path

    def process(self) -> bool:
        """
        Run the complete analysis pipeline

        Returns:
            bool: True if successful, False otherwise
        """
        from .threat_detector import ThreatDetector
        from ..models import ThreatDetection, AnalysisLog

        try:
            # Update status
            self.analysis.status = "processing"
            self.analysis.started_at = timezone.now()
            self.analysis.save(update_fields=["status", "started_at"])

            self._log("info", "Analysis started")

            # Initialize detector
            all_detections = []

            with ThreatDetector(self.image_path) as detector:
                # Run detection algorithms based on analysis type
                if self.analysis.analysis_type == "threat_detection":
                    self._log("info", "Running fire and explosion detection")
                    fire_detections = detector.detect_fires_explosions()
                    all_detections.extend(fire_detections)

                    self._log("info", "Running structural damage detection")
                    damage_detections = detector.detect_structural_damage()
                    all_detections.extend(damage_detections)

                    self._log("info", "Running vehicle concentration detection")
                    vehicle_detections = detector.detect_vehicle_concentrations()
                    all_detections.extend(vehicle_detections)

                elif self.analysis.analysis_type == "object_recognition":
                    self._log("info", "Running vehicle concentration detection")
                    vehicle_detections = detector.detect_vehicle_concentrations()
                    all_detections.extend(vehicle_detections)

                else:
                    self._log(
                        "warning",
                        f"Unknown analysis type: {self.analysis.analysis_type}",
                    )

            # Store detections in database
            threat_objects = []
            for detection in all_detections:
                try:
                    location_point = Point(
                        detection["location"][1],  # longitude
                        detection["location"][0],  # latitude
                        srid=4326,
                    )

                    threat = ThreatDetection(
                        analysis=self.analysis,
                        satellite_image=self.satellite_image,
                        threat_type=detection["threat_type"],
                        severity=detection["severity"],
                        location=location_point,
                        pixel_coordinates=detection["pixel_coords"],
                        confidence=detection["confidence"],
                        description=detection["description"],
                        technical_details=detection.get("technical_details", {}),
                    )
                    threat_objects.append(threat)

                except Exception as e:
                    self._log("error", f"Error creating threat object: {str(e)}")

            # Bulk create threats
            if threat_objects:
                ThreatDetection.objects.bulk_create(threat_objects)
                self._log("info", f"Created {len(threat_objects)} threat detections")

            # Generate summary
            summary = self._generate_summary(all_detections)

            # Calculate average confidence
            if all_detections:
                avg_confidence = sum(d["confidence"] for d in all_detections) / len(
                    all_detections
                )
            else:
                avg_confidence = 0.0

            # Update analysis result
            self.analysis.status = "completed"
            self.analysis.completed_at = timezone.now()
            self.analysis.summary = summary
            self.analysis.raw_data = {"detections": all_detections}
            self.analysis.confidence_score = avg_confidence
            self.analysis.threat_count = len(all_detections)
            self.analysis.calculate_processing_time()
            self.analysis.save()

            # Update satellite image analysis status
            self.satellite_image.analyzed = True
            self.satellite_image.analysis_count += 1
            self.satellite_image.save(update_fields=["analyzed", "analysis_count"])

            self._log(
                "info",
                f"Analysis completed successfully. Found {len(all_detections)} threats.",
            )

            return True

        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            self.analysis.status = "failed"
            self.analysis.error_message = str(e)
            self.analysis.completed_at = timezone.now()
            self.analysis.save(
                update_fields=["status", "error_message", "completed_at"]
            )

            self._log("error", f"Analysis failed: {str(e)}")

            return False

    def _generate_summary(self, detections: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary of analysis results"""
        if not detections:
            return "Analysis completed. No significant threats detected in the imagery."

        # Count by type
        type_counts = {}
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for detection in detections:
            threat_type = detection["threat_type"]
            severity = detection["severity"]

            type_counts[threat_type] = type_counts.get(threat_type, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Build summary
        summary_parts = [
            f"Analysis identified {len(detections)} potential threat(s):",
            "",
        ]

        # Critical threats first
        if severity_counts["critical"] > 0:
            summary_parts.append(
                f"⚠️ CRITICAL: {severity_counts['critical']} high-priority threat(s) requiring immediate attention"
            )

        if severity_counts["high"] > 0:
            summary_parts.append(
                f"🔴 HIGH: {severity_counts['high']} significant threat(s) detected"
            )

        if severity_counts["medium"] > 0:
            summary_parts.append(
                f"🟡 MEDIUM: {severity_counts['medium']} moderate concern(s) identified"
            )

        if severity_counts["low"] > 0:
            summary_parts.append(
                f"🔵 LOW: {severity_counts['low']} minor anomaly/anomalies detected"
            )

        summary_parts.append("")
        summary_parts.append("Threat Breakdown:")

        # Threat type descriptions
        threat_descriptions = {
            "fire": "Fire/Explosion Signatures",
            "explosion": "Explosion Sites",
            "structural_damage": "Structural Damage Areas",
            "vehicle_convoy": "Vehicle Concentrations/Convoys",
            "armed_group": "Armed Group Activity",
            "unusual_activity": "Unusual Activity Patterns",
        }

        for threat_type, count in sorted(
            type_counts.items(), key=lambda x: x[1], reverse=True
        ):
            desc = threat_descriptions.get(
                threat_type, threat_type.replace("_", " ").title()
            )
            summary_parts.append(f"  • {desc}: {count}")

        summary_parts.append("")
        summary_parts.append(
            "Recommendation: Review detected threats on the map for location details and priority response planning."
        )

        return "\n".join(summary_parts)

    def _log(self, level: str, message: str, details: Dict[str, Any] = None):
        """Create analysis log entry"""
        from ..models import AnalysisLog

        if details is None:
            details = {}

        AnalysisLog.objects.create(
            analysis=self.analysis, level=level, message=message, details=details
        )
