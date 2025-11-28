from django.contrib.gis.db import models
from django.core.validators import (
    FileExtensionValidator,
    MinValueValidator,
    MaxValueValidator,
)
from django.utils import timezone
from django.conf import settings
import os


class SatelliteImage(models.Model):
    """Model for storing satellite imagery metadata and cloud-optimized references"""

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("optimized", "Optimized"),
        ("failed", "Failed"),
    ]

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)

    # Original and optimized images
    original_image = models.FileField(
        upload_to="satellite/original/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=["tif", "tiff", "geotiff"])
        ],
        help_text="Upload GeoTIFF satellite imagery",
    )
    optimized_image = models.FileField(
        upload_to="satellite/optimized/%Y/%m/",
        blank=True,
        null=True,
        max_length=500,
        help_text="Cloud-optimized GeoTIFF (COG)",
    )
    thumbnail = models.ImageField(
        upload_to="satellite/thumbnails/%Y/%m/", blank=True, null=True, max_length=500
    )
    map_overlay = models.ImageField(
        upload_to="satellite/overlays/%Y/%m/",
        blank=True,
        null=True,
        max_length=500,
        help_text="PNG image for map overlay display",
    )

    # Geospatial information
    bounds = models.PolygonField(geography=True, null=True, blank=True)
    center_point = models.PointField(geography=True, null=True, blank=True)

    # Metadata
    acquisition_date = models.DateTimeField(
        null=True, blank=True, help_text="Date when the satellite captured this image"
    )
    upload_date = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_date = models.DateTimeField(auto_now=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_satellite_images",
    )

    # Image properties
    resolution = models.FloatField(
        null=True, blank=True, help_text="Ground sample distance in meters"
    )
    bands = models.IntegerField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True, help_text="Size in bytes")

    # Processing status
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="uploaded", db_index=True
    )
    processing_error = models.TextField(blank=True)

    # Analysis flags
    analyzed = models.BooleanField(default=False, db_index=True)
    analysis_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-upload_date"]
        indexes = [
            models.Index(fields=["-upload_date", "status"]),
            models.Index(fields=["analyzed", "-upload_date"]),
        ]
        verbose_name = "Satellite Image"
        verbose_name_plural = "Satellite Images"

    def __str__(self):
        return f"{self.name} - {self.upload_date.strftime('%Y-%m-%d')}"

    def get_bounds_coordinates(self):
        """Return bounds in [[lat1, lon1], [lat2, lon2]] format for frontend"""
        if self.bounds:
            coords = list(self.bounds.coords[0])
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return [[min(lats), min(lons)], [max(lats), max(lons)]]
        return None

    def delete(self, *args, **kwargs):
        """Override delete to remove associated files"""
        if self.original_image:
            try:
                if os.path.isfile(self.original_image.path):
                    os.remove(self.original_image.path)
            except Exception:
                pass
        if self.optimized_image:
            try:
                if os.path.isfile(self.optimized_image.path):
                    os.remove(self.optimized_image.path)
            except Exception:
                pass
        if self.thumbnail:
            try:
                if os.path.isfile(self.thumbnail.path):
                    os.remove(self.thumbnail.path)
            except Exception:
                pass
        if self.map_overlay:
            try:
                if os.path.isfile(self.map_overlay.path):
                    os.remove(self.map_overlay.path)
            except Exception:
                pass
        super().delete(*args, **kwargs)


class AnalysisResult(models.Model):
    """Model for storing analysis results performed on satellite images"""

    ANALYSIS_TYPES = [
        ("threat_detection", "Threat Detection"),
        ("change_detection", "Change Detection"),
        ("object_recognition", "Object Recognition"),
        ("terrain_analysis", "Terrain Analysis"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    satellite_image = models.ForeignKey(
        SatelliteImage, on_delete=models.CASCADE, related_name="analyses"
    )
    analysis_type = models.CharField(
        max_length=50, choices=ANALYSIS_TYPES, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Results
    summary = models.TextField(
        blank=True, help_text="Human-readable summary of analysis results"
    )
    raw_data = models.JSONField(
        default=dict, help_text="Detailed analysis data in JSON format"
    )
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    # Metrics
    threat_count = models.IntegerField(default=0)
    processing_time = models.FloatField(
        null=True, blank=True, help_text="Processing time in seconds"
    )

    # Error handling
    error_message = models.TextField(blank=True)

    # Analyst information
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_analyses",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "status"]),
            models.Index(fields=["satellite_image", "-created_at"]),
        ]
        verbose_name = "Analysis Result"
        verbose_name_plural = "Analysis Results"

    def __str__(self):
        return f"{self.analysis_type} - {self.satellite_image.name} - {self.status}"

    def calculate_processing_time(self):
        """Calculate and update processing time"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.processing_time = delta.total_seconds()
            self.save(update_fields=["processing_time"])


class ThreatDetection(models.Model):
    """Model for storing individual threat detections from analysis"""

    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    THREAT_TYPES = [
        ("explosion", "Explosion/Bomb Blast"),
        ("fire", "Fire/Smoke"),
        ("armed_group", "Armed Group Activity"),
        ("vehicle_convoy", "Vehicle Convoy"),
        ("structural_damage", "Structural Damage"),
        ("unusual_activity", "Unusual Activity"),
        ("camp_formation", "Camp Formation"),
        ("roadblock", "Roadblock/Checkpoint"),
    ]

    analysis = models.ForeignKey(
        AnalysisResult, on_delete=models.CASCADE, related_name="detections"
    )
    satellite_image = models.ForeignKey(
        SatelliteImage, on_delete=models.CASCADE, related_name="threats"
    )

    # Threat details
    threat_type = models.CharField(max_length=50, choices=THREAT_TYPES, db_index=True)
    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, default="medium", db_index=True
    )

    # Location
    location = models.PointField(geography=True)
    pixel_coordinates = models.JSONField(
        help_text="Pixel coordinates in the original image"
    )
    area = models.PolygonField(geography=True, null=True, blank=True)

    # Detection metrics
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Detection confidence score (0-1)",
    )

    # Description
    description = models.TextField(
        help_text="Plain language description for military personnel"
    )
    technical_details = models.JSONField(
        default=dict, help_text="Technical analysis details"
    )

    # Timestamps
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Status tracking
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_threats",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    # Response tracking
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_threats",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-detected_at", "-severity"]
        indexes = [
            models.Index(fields=["-detected_at", "severity"]),
            models.Index(fields=["threat_type", "-detected_at"]),
            models.Index(fields=["verified", "-detected_at"]),
        ]
        verbose_name = "Threat Detection"
        verbose_name_plural = "Threat Detections"

    def __str__(self):
        return f"{self.get_threat_type_display()} - {self.severity.upper()} - {self.detected_at.strftime('%Y-%m-%d %H:%M')}"

    def get_location_coordinates(self):
        """Return location as [latitude, longitude] for frontend"""
        if self.location:
            return [self.location.y, self.location.x]
        return None


class AnalysisLog(models.Model):
    """Model for logging analysis operations for audit purposes"""

    LOG_LEVELS = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("critical", "Critical"),
    ]

    analysis = models.ForeignKey(
        AnalysisResult, on_delete=models.CASCADE, related_name="logs"
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=20, choices=LOG_LEVELS, default="info")
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["analysis", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.level.upper()} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
