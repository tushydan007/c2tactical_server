from .views import SatelliteImageViewSet, AnalysisResultViewSet, ThreatDetectionViewSet
from rest_framework.routers import DefaultRouter


# API Router for satellite app
router = DefaultRouter()

router.register("images", SatelliteImageViewSet, basename="satelliteimage")
router.register("analyses", AnalysisResultViewSet, basename="analysisresult")
router.register("threats", ThreatDetectionViewSet, basename="threatdetection")


urlpatterns = router.urls
