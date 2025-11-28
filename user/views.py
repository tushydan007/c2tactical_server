from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

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
