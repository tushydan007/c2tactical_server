from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

User = get_user_model()


class UserCreateSerializer(BaseUserCreateSerializer):
    """Custom user registration serializer"""

    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}, min_length=8
    )

    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "rank",
            "unit",
            "phone_number",
        )
        extra_kwargs = {
            "password": {"write_only": True, "min_length": 8},
            "email": {"required": True},
            "first_name": {"required": True},
            "last_name": {"required": True},
        }

    def validate_email(self, value):
        """Validate email uniqueness"""
        # Normalize email
        normalized_email = value.lower().strip()

        if User.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError(
                "A user with this email address already exists."
            )
        return normalized_email

    def validate_password(self, value):
        """Validate password strength"""
        # Use Django's built-in password validators
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        # Additional custom validations
        if len(value) < 8:
            raise serializers.ValidationError(
                "Password must be at least 8 characters long."
            )

        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one digit."
            )

        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )

        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )

        return value

    def create(self, validated_data):
        """Create user with properly hashed password"""
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(BaseUserSerializer):
    """Custom user serializer for authenticated requests"""

    avatar_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "rank",
            "unit",
            "phone_number",
            "avatar",
            "avatar_url",
            "is_verified",
            "is_staff",
            "date_joined",
            "last_login",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "email",
            "date_joined",
            "last_login",
            "is_verified",
            "is_staff",
            "updated_at",
        )

    def get_avatar_url(self, obj):
        """Get full URL for avatar"""
        if obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
        return None

    def get_full_name(self, obj):
        """Get user's full name"""
        return obj.get_full_name()


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile"""

    avatar_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "rank",
            "unit",
            "phone_number",
            "avatar",
            "avatar_url",
        )

    def validate_avatar(self, value):
        """Validate avatar file size and type"""
        if value:
            # Check file size (5MB limit)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Avatar file size cannot exceed 5MB.")

            # Check file type
            allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
            if (
                hasattr(value, "content_type")
                and value.content_type not in allowed_types
            ):
                raise serializers.ValidationError(
                    "Only JPEG, PNG, and WebP images are allowed."
                )

        return value

    def get_avatar_url(self, obj):
        """Get full URL for avatar"""
        if obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
        return None

    def update(self, instance, validated_data):
        """Update user profile with avatar cleanup"""
        # If new avatar is provided and old one exists, delete old one
        if "avatar" in validated_data and instance.avatar:
            old_avatar = instance.avatar
            instance.avatar = None
            instance.save()
            old_avatar.delete(save=False)

        return super().update(instance, validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change endpoint"""

    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)

    def validate_old_password(self, value):
        """Validate old password is correct"""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate_new_password(self, value):
        """Validate new password strength"""
        try:
            validate_password(value, user=self.context["request"].user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        return value

    def save(self):
        """Update user password"""
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
