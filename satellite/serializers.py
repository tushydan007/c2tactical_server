from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import SatelliteImage, AnalysisResult, ThreatDetection, AnalysisLog


class SatelliteImageUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading satellite images"""

    class Meta:
        model = SatelliteImage
        fields = [
            "id",
            "name",
            "description",
            "original_image",
            "acquisition_date",
            "upload_date",
        ]
        read_only_fields = ["id", "upload_date"]


class SatelliteImageListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing satellite images"""

    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    map_overlay_url = serializers.SerializerMethodField()
    bounds = serializers.SerializerMethodField()
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True
    )

    class Meta:
        model = SatelliteImage
        fields = [
            "id",
            "name",
            "upload_date",
            "acquisition_date",
            "status",
            "analyzed",
            "analysis_count",
            "image_url",
            "thumbnail_url",
            "map_overlay_url",
            "bounds",
            "resolution",
            "file_size",
            "uploaded_by_email",
        ]
        read_only_fields = fields

    def get_image_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.optimized_image and request:
                return request.build_absolute_uri(obj.optimized_image.url)
            elif obj.original_image and request:
                return request.build_absolute_uri(obj.original_image.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to build absolute URI for image {obj.id}: {str(e)}")
            if obj.optimized_image:
                return obj.optimized_image.url
            elif obj.original_image:
                return obj.original_image.url
        return None

    def get_thumbnail_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.thumbnail and request:
                return request.build_absolute_uri(obj.thumbnail.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to build absolute URI for thumbnail {obj.id}: {str(e)}"
            )
            if obj.thumbnail:
                return obj.thumbnail.url
        return None

    def get_map_overlay_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.map_overlay and request:
                return request.build_absolute_uri(obj.map_overlay.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to build absolute URI for map overlay {obj.id}: {str(e)}"
            )
            if obj.map_overlay:
                return obj.map_overlay.url
        return None

    def get_bounds(self, obj):
        return obj.get_bounds_coordinates()


class SatelliteImageDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for satellite images"""

    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    map_overlay_url = serializers.SerializerMethodField()
    bounds = serializers.SerializerMethodField()
    center = serializers.SerializerMethodField()
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True
    )

    class Meta:
        model = SatelliteImage
        fields = "__all__"
        read_only_fields = [
            "id",
            "upload_date",
            "updated_date",
            "uploaded_by",
            "optimized_image",
            "thumbnail",
            "bounds",
            "center_point",
            "width",
            "height",
            "bands",
            "file_size",
            "status",
            "processing_error",
            "analyzed",
            "analysis_count",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.optimized_image and request:
                return request.build_absolute_uri(obj.optimized_image.url)
            elif obj.original_image and request:
                return request.build_absolute_uri(obj.original_image.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to build absolute URI for image {obj.id}: {str(e)}")
            if obj.optimized_image:
                return obj.optimized_image.url
            elif obj.original_image:
                return obj.original_image.url
        return None

    def get_thumbnail_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.thumbnail and request:
                return request.build_absolute_uri(obj.thumbnail.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to build absolute URI for thumbnail {obj.id}: {str(e)}"
            )
            if obj.thumbnail:
                return obj.thumbnail.url
        return None

    def get_map_overlay_url(self, obj):
        request = self.context.get("request")
        try:
            if obj.map_overlay and request:
                return request.build_absolute_uri(obj.map_overlay.url)
        except Exception as e:
            # Fallback to relative URL if build_absolute_uri fails
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to build absolute URI for map overlay {obj.id}: {str(e)}"
            )
            if obj.map_overlay:
                return obj.map_overlay.url
        return None

    def get_bounds(self, obj):
        return obj.get_bounds_coordinates()

    def get_center(self, obj):
        if obj.center_point:
            return [obj.center_point.y, obj.center_point.x]
        return None


class ThreatDetectionSerializer(GeoFeatureModelSerializer):
    """Serializer for threat detections with GeoJSON support"""

    location_coords = serializers.SerializerMethodField()
    threat_type_display = serializers.CharField(
        source="get_threat_type_display", read_only=True
    )
    severity_display = serializers.CharField(
        source="get_severity_display", read_only=True
    )
    image_name = serializers.CharField(source="satellite_image.name", read_only=True)

    class Meta:
        model = ThreatDetection
        geo_field = "location"
        fields = [
            "id",
            "analysis",
            "satellite_image",
            "image_name",
            "threat_type",
            "threat_type_display",
            "severity",
            "severity_display",
            "location_coords",
            "confidence",
            "description",
            "detected_at",
            "verified",
            "acknowledged",
            "notes",
        ]
        read_only_fields = ["id", "analysis", "satellite_image", "detected_at"]

    def get_location_coords(self, obj):
        return obj.get_location_coordinates()


class AnalysisLogSerializer(serializers.ModelSerializer):
    """Serializer for analysis logs"""

    class Meta:
        model = AnalysisLog
        fields = ["id", "timestamp", "level", "message", "details"]
        read_only_fields = fields


class AnalysisResultSerializer(serializers.ModelSerializer):
    """Serializer for analysis results"""

    detections = ThreatDetectionSerializer(many=True, read_only=True)
    logs = AnalysisLogSerializer(many=True, read_only=True)
    image_name = serializers.CharField(source="satellite_image.name", read_only=True)
    analysis_type_display = serializers.CharField(
        source="get_analysis_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    initiated_by_email = serializers.EmailField(
        source="initiated_by.email", read_only=True
    )

    class Meta:
        model = AnalysisResult
        fields = [
            "id",
            "satellite_image",
            "image_name",
            "analysis_type",
            "analysis_type_display",
            "status",
            "status_display",
            "created_at",
            "started_at",
            "completed_at",
            "summary",
            "raw_data",
            "confidence_score",
            "threat_count",
            "processing_time",
            "error_message",
            "initiated_by_email",
            "detections",
            "logs",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "started_at",
            "completed_at",
            "processing_time",
            "threat_count",
        ]
