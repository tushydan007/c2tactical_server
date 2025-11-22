"""
URL configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)

from satellite.views import (
    SatelliteImageViewSet,
    AnalysisResultViewSet,
    ThreatDetectionViewSet
)

# API Router
router = DefaultRouter()
router.register(r'satellite-images', SatelliteImageViewSet, basename='satellite-image')
router.register(r'analyses', AnalysisResultViewSet, basename='analysis')
router.register(r'threat-detections', ThreatDetectionViewSet, basename='threat-detection')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API
    path('api/', include(router.urls)),
    path('api/auth/', include('rest_framework.urls')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site customization
admin.site.site_header = "Military Intelligence System"
admin.site.site_title = "Military Intelligence Admin"
admin.site.index_title = "Satellite Analysis Administration"