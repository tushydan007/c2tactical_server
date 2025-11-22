from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import SatelliteImage, AnalysisResult, ThreatDetection, AnalysisLog
from .tasks import optimize_satellite_image, run_satellite_analysis


@admin.register(SatelliteImage)
class SatelliteImageAdmin(GISModelAdmin):
    """Enhanced admin interface for satellite images with analysis triggers"""
    
    list_display = [
        'name',
        'status_badge',
        'upload_date',
        'resolution',
        'file_size_display',
        'analyzed_badge',
        'analysis_count',
        'image_preview'
    ]
    list_filter = ['status', 'analyzed', 'upload_date', 'acquisition_date']
    search_fields = ['name', 'description']
    readonly_fields = [
        'upload_date',
        'updated_date',
        'status',
        'optimized_image',
        'thumbnail',
        'bounds',
        'center_point',
        'width',
        'height',
        'bands',
        'file_size',
        'processing_error',
        'analyzed',
        'analysis_count',
        'image_preview_large'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'acquisition_date')
        }),
        ('Image Files', {
            'fields': ('original_image', 'optimized_image', 'thumbnail', 'image_preview_large')
        }),
        ('Geospatial Data', {
            'fields': ('bounds', 'center_point'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'resolution',
                'width',
                'height',
                'bands',
                'file_size',
                'upload_date',
                'updated_date',
                'uploaded_by'
            ),
            'classes': ('collapse',)
        }),
        ('Processing Status', {
            'fields': ('status', 'processing_error', 'analyzed', 'analysis_count')
        }),
    )
    
    actions = [
        'trigger_optimization',
        'run_threat_detection_analysis',
        'run_change_detection_analysis'
    ]
    
    def status_badge(self, obj):
        colors = {
            'uploaded': 'gray',
            'processing': 'blue',
            'optimized': 'green',
            'failed': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def analyzed_badge(self, obj):
        if obj.analyzed:
            return format_html(
                '<span style="background-color: green; color: white; '
                'padding: 3px 10px; border-radius: 3px; font-size: 11px;">✓ YES</span>'
            )
        return format_html(
            '<span style="background-color: orange; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px;">✗ NO</span>'
        )
    analyzed_badge.short_description = 'Analyzed'
    
    def file_size_display(self, obj):
        if obj.file_size:
            size_mb = obj.file_size / (1024 * 1024)
            return f'{size_mb:.2f} MB'
        return 'N/A'
    file_size_display.short_description = 'File Size'
    
    def image_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 100px;" />',
                obj.thumbnail.url
            )
        return 'No preview'
    image_preview.short_description = 'Preview'
    
    def image_preview_large(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-width: 600px; max-height: 400px;" />',
                obj.thumbnail.url
            )
        return 'No preview available'
    image_preview_large.short_description = 'Image Preview'
    
    def trigger_optimization(self, request, queryset):
        """Admin action to trigger image optimization"""
        count = 0
        for image in queryset:
            if image.status == 'uploaded':
                optimize_satellite_image.delay(image.id)
                count += 1
        
        self.message_user(
            request,
            f'Optimization triggered for {count} image(s).'
        )
    trigger_optimization.short_description = 'Optimize selected images'
    
    def run_threat_detection_analysis(self, request, queryset):
        """Admin action to run threat detection analysis"""
        count = 0
        for image in queryset:
            if image.status == 'optimized':
                analysis = AnalysisResult.objects.create(
                    satellite_image=image,
                    analysis_type='threat_detection',
                    initiated_by=request.user,
                    status='pending'
                )
                run_satellite_analysis.delay(analysis.id)
                count += 1
        
        self.message_user(
            request,
            f'Threat detection analysis initiated for {count} image(s).'
        )
    run_threat_detection_analysis.short_description = 'Run threat detection analysis'
    
    def run_change_detection_analysis(self, request, queryset):
        """Admin action to run change detection analysis"""
        count = 0
        for image in queryset:
            if image.status == 'optimized':
                analysis = AnalysisResult.objects.create(
                    satellite_image=image,
                    analysis_type='change_detection',
                    initiated_by=request.user,
                    status='pending'
                )
                run_satellite_analysis.delay(analysis.id)
                count += 1
        
        self.message_user(
            request,
            f'Change detection analysis initiated for {count} image(s).'
        )
    run_change_detection_analysis.short_description = 'Run change detection analysis'


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    """Admin interface for analysis results"""
    
    list_display = [
        'id',
        'satellite_image',
        'analysis_type',
        'status_badge',
        'threat_count',
        'confidence_score',
        'created_at',
        'processing_time_display'
    ]
    list_filter = ['status', 'analysis_type', 'created_at']
    search_fields = ['satellite_image__name', 'summary']
    readonly_fields = [
        'created_at',
        'started_at',
        'completed_at',
        'processing_time',
        'threat_count'
    ]
    
    fieldsets = (
        ('Analysis Information', {
            'fields': (
                'satellite_image',
                'analysis_type',
                'status',
                'initiated_by'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at', 'processing_time')
        }),
        ('Results', {
            'fields': ('summary', 'raw_data', 'confidence_score', 'threat_count')
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'pending': 'gray',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def processing_time_display(self, obj):
        if obj.processing_time:
            return f'{obj.processing_time:.2f}s'
        return 'N/A'
    processing_time_display.short_description = 'Processing Time'


@admin.register(ThreatDetection)
class ThreatDetectionAdmin(GISModelAdmin):
    """Admin interface for threat detections"""
    
    list_display = [
        'id',
        'threat_type',
        'severity_badge',
        'confidence_display',
        'detected_at',
        'verified_badge',
        'acknowledged_badge'
    ]
    list_filter = [
        'severity',
        'threat_type',
        'verified',
        'acknowledged',
        'detected_at'
    ]
    search_fields = ['description', 'satellite_image__name']
    readonly_fields = [
        'analysis',
        'satellite_image',
        'detected_at',
        'confidence',
        'pixel_coordinates',
        'technical_details'
    ]
    
    fieldsets = (
        ('Detection Information', {
            'fields': (
                'analysis',
                'satellite_image',
                'threat_type',
                'severity',
                'confidence',
                'detected_at'
            )
        }),
        ('Location', {
            'fields': ('location', 'pixel_coordinates', 'area')
        }),
        ('Description', {
            'fields': ('description', 'technical_details')
        }),
        ('Verification', {
            'fields': (
                'verified',
                'verified_by',
                'verified_at',
                'acknowledged',
                'acknowledged_by',
                'acknowledged_at',
                'notes'
            )
        }),
    )
    
    def severity_badge(self, obj):
        colors = {
            'low': '#3b82f6',
            'medium': '#f59e0b',
            'high': '#f97316',
            'critical': '#ef4444',
        }
        color = colors.get(obj.severity, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.severity.upper()
        )
    severity_badge.short_description = 'Severity'
    
    def confidence_display(self, obj):
        percentage = int(obj.confidence * 100)
        color = '#22c55e' if percentage >= 80 else '#f59e0b' if percentage >= 60 else '#ef4444'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color,
            percentage
        )
    confidence_display.short_description = 'Confidence'
    
    def verified_badge(self, obj):
        if obj.verified:
            return format_html('<span style="color: green; font-weight: bold;">✓</span>')
        return format_html('<span style="color: gray;">✗</span>')
    verified_badge.short_description = 'Verified'
    
    def acknowledged_badge(self, obj):
        if obj.acknowledged:
            return format_html('<span style="color: green; font-weight: bold;">✓</span>')
        return format_html('<span style="color: gray;">✗</span>')
    acknowledged_badge.short_description = 'Acknowledged'


@admin.register(AnalysisLog)
class AnalysisLogAdmin(admin.ModelAdmin):
    """Admin interface for analysis logs"""
    
    list_display = ['id', 'analysis', 'level_badge', 'message_preview', 'timestamp']
    list_filter = ['level', 'timestamp']
    search_fields = ['message', 'analysis__satellite_image__name']
    readonly_fields = ['analysis', 'timestamp', 'level', 'message', 'details']
    
    def level_badge(self, obj):
        colors = {
            'info': 'blue',
            'warning': 'orange',
            'error': 'red',
            'critical': 'darkred',
        }
        color = colors.get(obj.level, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.level.upper()
        )
    level_badge.short_description = 'Level'
    
    def message_preview(self, obj):
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'