from django.apps import AppConfig


class SatelliteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'satellite'

    def ready(self):
        """Import signals when app is ready"""
        import satellite.signals  # noqa
