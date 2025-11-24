from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'  # Changed from 'users' to 'user'
    verbose_name = 'User Management'
    
    def ready(self):
        """Import signals when app is ready"""
        try:
            import user.signals  # noqa
        except ImportError:
            pass