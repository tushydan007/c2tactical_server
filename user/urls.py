from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileViewSet

router = DefaultRouter()
router.register("profile", UserProfileViewSet, basename="profile")

urlpatterns = [
    # Djoser authentication endpoints
    path("auth/", include("djoser.urls")),
    path("auth/", include("djoser.urls.jwt")),
    # Custom profile endpoints
    path("", include(router.urls)),
]
