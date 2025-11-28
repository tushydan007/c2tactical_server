# from rest_framework import status, viewsets
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from django.contrib.auth import get_user_model
# from .serializers import UserSerializer, UserProfileUpdateSerializer

# User = get_user_model()


# class UserProfileViewSet(viewsets.GenericViewSet):
#     """ViewSet for user profile management"""

#     permission_classes = [IsAuthenticated]
#     serializer_class = UserSerializer

#     def get_queryset(self):
#         return User.objects.filter(id=self.request.user.id)

#     @action(detail=False, methods=['get'])
#     def me(self, request):
#         """Get current user's profile"""
#         # Debug logging
#         logger.info(f"User profile request from: {request.user}")
#         logger.info(f"Is authenticated: {request.user.is_authenticated}")
#         logger.info(f"Auth header: {request.META.get('HTTP_AUTHORIZATION', 'None')}")

#         if not request.user.is_authenticated:
#             return Response(
#                 {'detail': 'Authentication credentials were not provided.'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
#         serializer = self.get_serializer(request.user)
#         return Response(serializer.data)

#     @action(detail=False, methods=['put', 'patch'])
#     def update_profile(self, request):
#         """Update current user's profile"""
#         user = request.user
#         serializer = UserProfileUpdateSerializer(
#             user,
#             data=request.data,
#             partial=request.method == 'PATCH'
#         )

#         if serializer.is_valid():
#             serializer.save()
#             return Response(
#                 UserSerializer(user, context={'request': request}).data
#             )

#         return Response(
#             serializer.errors,
#             status=status.HTTP_400_BAD_REQUEST
#         )

#     @action(detail=False, methods=['post'])
#     def upload_avatar(self, request):
#         """Upload user avatar"""
#         user = request.user

#         if 'avatar' not in request.FILES:
#             return Response(
#                 {'error': 'No avatar file provided'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         avatar = request.FILES['avatar']

#         # Validate file size
#         if avatar.size > 5 * 1024 * 1024:
#             return Response(
#                 {'error': 'Avatar file size cannot exceed 5MB'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # Validate file type
#         allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
#         if avatar.content_type not in allowed_types:
#             return Response(
#                 {'error': 'Only JPEG and PNG images are allowed'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # Delete old avatar if exists
#         if user.avatar:
#             user.avatar.delete(save=False)

#         # Save new avatar
#         user.avatar = avatar
#         user.save()

#         serializer = UserSerializer(user, context={'request': request})
#         return Response(serializer.data)

#     @action(detail=False, methods=['delete'])
#     def delete_avatar(self, request):
#         """Delete user avatar"""
#         user = request.user

#         if user.avatar:
#             user.avatar.delete()
#             user.save()

#         return Response(status=status.HTTP_204_NO_CONTENT)


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
