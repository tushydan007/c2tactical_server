"""
Celery tasks for asynchronous processing
"""

from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def optimize_satellite_image(self, image_id: int):
    """
    Celery task to optimize satellite image (create COG and thumbnail)

    Args:
        image_id: SatelliteImage model ID
    """
    from .models import SatelliteImage
    from .analysis.image_optimizer import optimize_satellite_image_file

    try:
        satellite_image = SatelliteImage.objects.get(id=image_id)
        logger.info(
            f"Starting optimization for image {image_id}: {satellite_image.name}"
        )

        success = optimize_satellite_image_file(satellite_image)

        if success:
            logger.info(f"Successfully optimized image {image_id}")
            return {"status": "success", "image_id": image_id}
        else:
            raise Exception("Optimization failed")

    except SatelliteImage.DoesNotExist:
        logger.error(f"SatelliteImage {image_id} does not exist")
        return {"status": "error", "message": "Image not found"}

    except Exception as e:
        logger.error(f"Error optimizing image {image_id}: {str(e)}")
        # Retry task
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def run_satellite_analysis(self, analysis_id: int):
    """
    Celery task to run satellite image analysis

    Args:
        analysis_id: AnalysisResult model ID
    """
    from .models import AnalysisResult
    from .analysis.processors import AnalysisProcessor

    try:
        analysis = AnalysisResult.objects.select_related("satellite_image").get(
            id=analysis_id
        )
        logger.info(
            f"Starting analysis {analysis_id} for image {analysis.satellite_image.name}"
        )

        processor = AnalysisProcessor(analysis)
        success = processor.process()

        if success:
            logger.info(f"Successfully completed analysis {analysis_id}")
            return {
                "status": "success",
                "analysis_id": analysis_id,
                "threat_count": analysis.threat_count,
            }
        else:
            raise Exception("Analysis processing failed")

    except AnalysisResult.DoesNotExist:
        logger.error(f"AnalysisResult {analysis_id} does not exist")
        return {"status": "error", "message": "Analysis not found"}

    except Exception as e:
        logger.error(f"Error running analysis {analysis_id}: {str(e)}")
        # Retry task
        raise self.retry(exc=e)


@shared_task
def cleanup_old_analyses():
    """
    Periodic task to clean up old analysis results
    Run this daily to maintain database performance
    """
    from django.utils import timezone
    from datetime import timedelta
    from .models import AnalysisResult

    try:
        # Delete analyses older than 90 days
        cutoff_date = timezone.now() - timedelta(days=90)
        old_analyses = AnalysisResult.objects.filter(
            created_at__lt=cutoff_date, status__in=["completed", "failed"]
        )

        count = old_analyses.count()
        old_analyses.delete()

        logger.info(f"Cleaned up {count} old analysis results")
        return {"status": "success", "cleaned": count}

    except Exception as e:
        logger.error(f"Error cleaning up old analyses: {str(e)}")
        return {"status": "error", "message": str(e)}
