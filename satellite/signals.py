"""
Django signals for satellite image processing
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import logging

from .models import SatelliteImage, AnalysisResult
from .tasks import optimize_satellite_image, run_satellite_analysis

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SatelliteImage)
def auto_optimize_satellite_image(sender, instance, created, **kwargs):
    """
    Automatically trigger image optimization after upload
    """
    if created and instance.status == 'uploaded':
        logger.info(f'Triggering optimization for new image {instance.id}: {instance.name}')
        # Queue optimization task
        optimize_satellite_image.delay(instance.id)


@receiver(post_save, sender=AnalysisResult)
def auto_run_analysis_when_image_optimized(sender, instance, created, **kwargs):
    """
    Automatically trigger threat detection analysis after image optimization completes
    This hook is called when analysis is created via the analyze endpoint
    """
    if created and instance.status == 'pending':
        logger.info(f'Triggering analysis task {instance.id} for image {instance.satellite_image.id}')
        # Queue analysis task
        run_satellite_analysis.delay(instance.id)
