from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, UserProfileUpdateSerializer

User = get_user_model()


class UserProfileViewSet(viewsets.GenericViewSet):
    """ViewSet for user profile management"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    
    def get_queryset(self):
        return User.objects.filter(id=self.request.user.id)
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['put', 'patch'])
    def update_profile(self, request):
        """Update current user's profile"""
        user = request.user
        serializer = UserProfileUpdateSerializer(
            user,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(
                UserSerializer(user, context={'request': request}).data
            )
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def upload_avatar(self, request):
        """Upload user avatar"""
        user = request.user
        
        if 'avatar' not in request.FILES:
            return Response(
                {'error': 'No avatar file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        avatar = request.FILES['avatar']
        
        # Validate file size
        if avatar.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'Avatar file size cannot exceed 5MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/jpg']
        if avatar.content_type not in allowed_types:
            return Response(
                {'error': 'Only JPEG and PNG images are allowed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete old avatar if exists
        if user.avatar:
            user.avatar.delete(save=False)
        
        # Save new avatar
        user.avatar = avatar
        user.save()
        
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['delete'])
    def delete_avatar(self, request):
        """Delete user avatar"""
        user = request.user
        
        if user.avatar:
            user.avatar.delete()
            user.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)