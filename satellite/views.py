
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
import logging

from .models import SatelliteImage, AnalysisResult, ThreatDetection
from .serializers import (
    SatelliteImageListSerializer,
    SatelliteImageDetailSerializer,
    AnalysisResultSerializer,
    ThreatDetectionSerializer
)
from .tasks import run_satellite_analysis

logger = logging.getLogger(__name__)


class SatelliteImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing satellite images.
    Provides optimized queries with caching for performance.
    """
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'analyzed']
    search_fields = ['name', 'description']
    ordering_fields = ['upload_date', 'acquisition_date', 'name']
    ordering = ['-upload_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SatelliteImageDetailSerializer
        return SatelliteImageListSerializer
    
    def get_queryset(self):
        """Optimized queryset with select_related for performance"""
        queryset = SatelliteImage.objects.select_related('uploaded_by').all()
        
        # Filter by status if provided
        status_param = self.request.query_params.get('status', None)
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by date range if provided
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        
        if date_from:
            queryset = queryset.filter(upload_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(upload_date__lte=date_to)
        
        return queryset
    
    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_headers('Authorization'))
    def list(self, request, *args, **kwargs):
        """Cached list endpoint"""
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        """
        Trigger analysis on a satellite image.
        This action initiates an asynchronous Celery task.
        """
        satellite_image = self.get_object()
        
        # Check if image is ready for analysis
        if satellite_image.status != 'optimized':
            return Response(
                {'error': 'Image must be optimized before analysis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get analysis type from request
        analysis_type = request.data.get('analysis_type', 'threat_detection')
        
        # Create analysis record
        analysis = AnalysisResult.objects.create(
            satellite_image=satellite_image,
            analysis_type=analysis_type,
            initiated_by=request.user,
            status='pending'
        )
        
        # Trigger async task
        try:
            task = run_satellite_analysis.delay(analysis.id)
            logger.info(f'Analysis task {task.id} initiated for image {satellite_image.id}')
            
            return Response({
                'message': 'Analysis initiated successfully',
                'analysis_id': analysis.id,
                'task_id': task.id,
                'status': 'pending'
            }, status=status.HTTP_202_ACCEPTED)
        
        except Exception as e:
            logger.error(f'Error initiating analysis: {str(e)}')
            analysis.status = 'failed'
            analysis.error_message = str(e)
            analysis.save()
            
            return Response(
                {'error': f'Failed to initiate analysis: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def analyses(self, request, pk=None):
        """Get all analyses for a specific satellite image"""
        satellite_image = self.get_object()
        analyses = satellite_image.analyses.all()
        serializer = AnalysisResultSerializer(
            analyses,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)


class AnalysisResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing analysis results.
    Provides detailed analysis data and threat detections.
    """
    
    serializer_class = AnalysisResultSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'analysis_type', 'satellite_image']
    ordering_fields = ['created_at', 'completed_at', 'threat_count']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Optimized queryset with prefetch for related objects"""
        return AnalysisResult.objects.select_related(
            'satellite_image',
            'initiated_by'
        ).prefetch_related(
            'detections',
            'logs'
        ).all()
    
    @method_decorator(cache_page(60 * 2))  # Cache for 2 minutes
    @method_decorator(vary_on_headers('Authorization'))
    def retrieve(self, request, *args, **kwargs):
        """Cached retrieve endpoint"""
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    def status_check(self, request, pk=None):
        """Quick status check without full serialization"""
        analysis = self.get_object()
        return Response({
            'id': analysis.id,
            'status': analysis.status,
            'threat_count': analysis.threat_count,
            'processing_time': analysis.processing_time,
            'completed_at': analysis.completed_at
        })


class ThreatDetectionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing threat detections.
    Provides filtering by severity, type, and verification status.
    """
    
    serializer_class = ThreatDetectionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['severity', 'threat_type', 'verified', 'acknowledged']
    ordering_fields = ['detected_at', 'confidence', 'severity']
    ordering = ['-detected_at']
    
    def get_queryset(self):
        """Optimized queryset with spatial filtering support"""
        queryset = ThreatDetection.objects.select_related(
            'analysis',
            'satellite_image'
        ).all()
        
        # Filter by severity levels
        min_severity = self.request.query_params.get('min_severity', None)
        if min_severity:
            severity_order = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
            if min_severity in severity_order:
                min_val = severity_order[min_severity]
                filtered_severities = [k for k, v in severity_order.items() if v >= min_val]
                queryset = queryset.filter(severity__in=filtered_severities)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        
        if date_from:
            queryset = queryset.filter(detected_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(detected_at__lte=date_to)
        
        return queryset
    
    @method_decorator(cache_page(60 * 1))  # Cache for 1 minute
    @method_decorator(vary_on_headers('Authorization'))
    def list(self, request, *args, **kwargs):
        """Cached list endpoint with shorter cache time for real-time updates"""
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Mark a threat detection as verified"""
        threat = self.get_object()
        threat.verified = True
        threat.verified_by = request.user
        threat.verified_at = timezone.now()
        threat.save()
        
        # Invalidate cache
        cache.delete_many([
            'threat_list_*',
            f'threat_detail_{pk}'
        ])
        
        serializer = self.get_serializer(threat)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Mark a threat detection as acknowledged"""
        threat = self.get_object()
        threat.acknowledged = True
        threat.acknowledged_by = request.user
        threat.acknowledged_at = timezone.now()
        
        # Add notes if provided
        notes = request.data.get('notes', '')
        if notes:
            threat.notes = notes
        
        threat.save()
        
        # Invalidate cache
        cache.delete_many([
            'threat_list_*',
            f'threat_detail_{pk}'
        ])
        
        serializer = self.get_serializer(threat)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics of threat detections"""
        cache_key = 'threat_summary'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        queryset = self.get_queryset()
        
        summary_data = {
            'total': queryset.count(),
            'by_severity': {
                'critical': queryset.filter(severity='critical').count(),
                'high': queryset.filter(severity='high').count(),
                'medium': queryset.filter(severity='medium').count(),
                'low': queryset.filter(severity='low').count(),
            },
            'by_type': {},
            'verified_count': queryset.filter(verified=True).count(),
            'acknowledged_count': queryset.filter(acknowledged=True).count(),
        }
        
        # Get counts by threat type
        for threat_type, _ in ThreatDetection.THREAT_TYPES:
            count = queryset.filter(threat_type=threat_type).count()
            if count > 0:
                summary_data['by_type'][threat_type] = count
        
        # Cache for 2 minutes
        cache.set(cache_key, summary_data, 120)
        
        return Response(summary_data)