from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from .models import UserPreferences
from rest_framework_simplejwt.tokens import RefreshToken    

from .serializers import (
    UserSerializer,
    UserProfileUpdateSerializer,
    ChangePasswordSerializer,
)

User = get_user_model()


class UserProfileViewSet(viewsets.GenericViewSet):
    """
    ViewSet for managing user profiles

    Endpoints:
    - GET /api/user/profile/me/ - Get current user profile
    - PUT /api/user/profile/me/ - Update current user profile
    - PATCH /api/user/profile/me/ - Partial update current user profile
    - POST /api/user/profile/change-password/ - Change password
    - DELETE /api/user/profile/delete-avatar/ - Delete user avatar
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        """Return appropriate serializer class"""
        if self.action == "change_password":
            return ChangePasswordSerializer
        elif self.action in ["update", "partial_update"]:
            return UserProfileUpdateSerializer
        return UserSerializer

    def get_object(self):
        """Return the current authenticated user"""
        return self.request.user

    @extend_schema(
        summary="Get current user profile",
        description="Retrieve the profile information of the currently authenticated user",
        responses={200: UserSerializer},
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Get current user profile"""
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="Update user profile",
        description="Update the profile information of the currently authenticated user",
        request=UserProfileUpdateSerializer,
        responses={200: UserSerializer},
    )
    @extend_schema(
        summary="Logout user",
        description="Blacklist the refresh token to logout the user",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "refresh": {
                        "type": "string",
                        "description": "Refresh token to blacklist",
                    }
                },
                "required": ["refresh"],
            }
        },
        responses={
            205: {"description": "Successfully logged out"},
            400: {"description": "Invalid token or token already blacklisted"},
        },
    )
    @action(detail=False, methods=["put", "patch"], url_path="me")
    def update_profile(self, request):
        """Update current user profile"""
        partial = request.method == "PATCH"
        serializer = UserProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            serializer.save()

        # Return updated user data
        user_serializer = UserSerializer(request.user, context={"request": request})
        return Response(user_serializer.data)

    @extend_schema(
        summary="Change password",
        description="Change the password of the currently authenticated user",
        request=ChangePasswordSerializer,
        responses={
            200: {"description": "Password changed successfully"},
            400: {"description": "Invalid data"},
        },
    )
    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Password changed successfully."}, status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Delete user avatar",
        description="Delete the avatar image of the currently authenticated user",
        responses={
            200: {"description": "Avatar deleted successfully"},
            404: {"description": "No avatar to delete"},
        },
    )
    @action(detail=False, methods=["delete"], url_path="delete-avatar")
    def delete_avatar(self, request):
        """Delete user avatar"""
        user = request.user

        if not user.avatar:
            return Response(
                {"detail": "No avatar to delete."}, status=status.HTTP_404_NOT_FOUND
            )

        # Delete the avatar file
        user.avatar.delete(save=False)
        user.avatar = None
        user.save()

        return Response(
            {"detail": "Avatar deleted successfully."}, status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Get user statistics",
        description="Get statistics about the user's account",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Get user statistics"""
        user = request.user

        stats = {
            "account_age_days": (user.date_joined.now() - user.date_joined).days,
            "is_verified": user.is_verified,
            "has_avatar": bool(user.avatar),
            "profile_completion": self._calculate_profile_completion(user),
        }

        return Response(stats)

    def _calculate_profile_completion(self, user):
        """Calculate profile completion percentage"""
        fields = ["first_name", "last_name", "rank", "unit", "phone_number", "avatar"]
        filled = sum(1 for field in fields if getattr(user, field))
        return round((filled / len(fields)) * 100, 2)

    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        """
        Logout user by blacklisting the refresh token

        Note: Requires 'rest_framework_simplejwt.token_blacklist' in INSTALLED_APPS
        and migrations to be run for the blacklist app.
        """
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except TokenError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"detail": "An error occurred during logout."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    
    @extend_schema(
    summary="Get user statistics",
    description="Get comprehensive statistics about the user's activity",
    responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Get user statistics including activity metrics"""
        user = request.user
        
        # Calculate account age
        account_age_days = (timezone.now() - user.date_joined).days
        
        # Get statistics from related models
        # Import your models at the top of the file
        from satellite.models import SatelliteImage, ThreatDetection, AnalysisResult
        
        # Count user's uploads
        images_uploaded = SatelliteImage.objects.filter(
            uploaded_by=user
        ).count()
        
        # Count threats detected in user's analyses
        threats_detected = ThreatDetection.objects.filter(
            analysis__initiated_by=user
        ).count()
        
        # Count completed analyses
        analyses_completed = AnalysisResult.objects.filter(
            initiated_by=user,
            status='completed'
        ).count()
        
        # Calculate days active (days with any activity)
        # This is a simplified version - you may want to track this differently
        last_30_days = timezone.now() - timedelta(days=30)
        activity_days = AnalysisResult.objects.filter(
            initiated_by=user,
            created_at__gte=last_30_days
        ).dates('created_at', 'day').count()
        
        # Calculate profile completion
        profile_fields = ['first_name', 'last_name', 'rank', 'unit', 'phone_number', 'avatar']
        filled_fields = sum(1 for field in profile_fields if getattr(user, field))
        profile_completion = round((filled_fields / len(profile_fields)) * 100, 2)
        
        stats = {
            'images_uploaded': images_uploaded,
            'threats_detected': threats_detected,
            'analyses_completed': analyses_completed,
            'days_active': activity_days,
            'account_age_days': account_age_days,
            'profile_completion': profile_completion,
        }
        
        return Response(stats)


    @extend_schema(
    summary="Get recent activity",
    description="Get recent user activity including uploads, analyses, and threats",
    parameters=[
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Number of activities to return (default: 10)'
        )
    ],
    responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='activity')
    def activity(self, request):
        """Get recent user activity"""
        user = request.user
        limit = int(request.query_params.get('limit', 10))
        
        from satellite.models import SatelliteImage, ThreatDetection, AnalysisResult
        
        activities = []
        
        # Get recent image uploads
        recent_uploads = SatelliteImage.objects.filter(
            uploaded_by=user
        ).order_by('-upload_date')[:limit]
        
        for upload in recent_uploads:
            activities.append({
                'id': f'upload_{upload.id}',
                'type': 'upload',
                'description': f'Uploaded satellite image - {upload.name}',
                'timestamp': upload.upload_date.isoformat(),
                'created_at': upload.upload_date.isoformat(),
            })
        
        # Get recent analyses - FIXED: Use get_analysis_type_display() method
        recent_analyses = AnalysisResult.objects.filter(
            initiated_by=user,
            status='completed'
        ).order_by('-completed_at')[:limit]
        
        for analysis in recent_analyses:
            activities.append({
                'id': f'analysis_{analysis.id}',
                'type': 'analysis',
                'description': f'Completed {analysis.get_analysis_type_display()} analysis',  # FIXED
                'timestamp': analysis.completed_at.isoformat() if analysis.completed_at else analysis.created_at.isoformat(),
                'created_at': analysis.created_at.isoformat(),
            })
        
        # Get recent threat verifications - FIXED: Use get_severity_display() and get_threat_type_display()
        recent_threats = ThreatDetection.objects.filter(
            analysis__initiated_by=user,
            verified=True
        ).order_by('-detected_at')[:limit]
        
        for threat in recent_threats:
            activities.append({
                'id': f'threat_{threat.id}',
                'type': 'threat',
                'description': f'Verified {threat.get_severity_display()} threat - {threat.get_threat_type_display()}',  # FIXED
                'timestamp': threat.detected_at.isoformat(),
                'created_at': threat.detected_at.isoformat(),
            })
        
        # Sort all activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Return only the requested number of activities
        return Response({
            'results': activities[:limit]
        })


    @extend_schema(
        summary="Get user preferences",
        description="Get user preferences including notifications, theme, and language",
        responses={200: OpenApiTypes.OBJECT}
    )
    @action(detail=False, methods=['get'], url_path='preferences')
    def get_preferences(self, request):
        user = request.user
        try:
            user_prefs = UserPreferences.objects.get(user=user)
            preferences = {
                'theme': user_prefs.theme,
                'language': user_prefs.language,
                'timezone': user_prefs.timezone,
                'notifications': {
                    'email_notifications': user_prefs.email_notifications,
                    'push_notifications': user_prefs.push_notifications,
                    'threat_alerts': user_prefs.threat_alerts,
                    'weekly_reports': user_prefs.weekly_reports,
                }
            }
        except UserPreferences.DoesNotExist:
            # Return defaults
            preferences = {
                'theme': 'dark',
                'language': 'en',
                'timezone': 'UTC',
                'notifications': {
                    'email_notifications': True,
                    'push_notifications': True,
                    'threat_alerts': True,
                    'weekly_reports': False,
                }
            }
            # Create default preferences
            UserPreferences.objects.create(user=user)
        
        return Response(preferences)


    @extend_schema(
        summary="Update user preferences",
        description="Update user preferences including notifications, theme, and language",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT}
    )
    
    @action(detail=False, methods=['patch'], url_path='preferences')
    def update_preferences(self, request):
        user = request.user
        data = request.data
        
        user_prefs, created = UserPreferences.objects.get_or_create(user=user)
        
        if 'theme' in data:
            user_prefs.theme = data['theme']
        if 'language' in data:
            user_prefs.language = data['language']
        if 'timezone' in data:
            user_prefs.timezone = data['timezone']
        if 'notifications' in data:
            notifications = data['notifications']
            user_prefs.email_notifications = notifications.get('email_notifications', user_prefs.email_notifications)
            user_prefs.push_notifications = notifications.get('push_notifications', user_prefs.push_notifications)
            user_prefs.threat_alerts = notifications.get('threat_alerts', user_prefs.threat_alerts)
            user_prefs.weekly_reports = notifications.get('weekly_reports', user_prefs.weekly_reports)
        
        user_prefs.save()
        
        return Response({
            'theme': user_prefs.theme,
            'language': user_prefs.language,
            'timezone': user_prefs.timezone,
            'notifications': {
                'email_notifications': user_prefs.email_notifications,
                'push_notifications': user_prefs.push_notifications,
                'threat_alerts': user_prefs.threat_alerts,
                'weekly_reports': user_prefs.weekly_reports,
            }
        })