from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.html import format_html

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom user admin interface"""
    
    list_display = [
        'email',
        'full_name_display',
        'rank',
        'unit',
        'is_active',
        'is_verified',
        'is_staff',
        'date_joined_display'
    ]
    list_filter = [
        'is_active',
        'is_staff',
        'is_superuser',
        'is_verified',
        'date_joined'
    ]
    search_fields = ['email', 'first_name', 'last_name', 'rank', 'unit']
    ordering = ['-date_joined']
    
    fieldsets = (
        (None, {
            'fields': ('email', 'password')
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone_number', 'avatar')
        }),
        ('Military Information', {
            'fields': ('rank', 'unit')
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'is_verified',
                'groups',
                'user_permissions'
            )
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'password1',
                'password2',
                'first_name',
                'last_name',
                'is_active',
                'is_staff'
            )
        }),
    )
    
    readonly_fields = ['date_joined', 'last_login']
    
    def full_name_display(self, obj):
        """Display full name"""
        return obj.get_full_name()
    full_name_display.short_description = 'Full Name'
    
    def date_joined_display(self, obj):
        """Display formatted join date"""
        return obj.date_joined.strftime('%Y-%m-%d %H:%M')
    date_joined_display.short_description = 'Date Joined'
    date_joined_display.admin_order_field = 'date_joined'