from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
import os
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for when a user is created or updated
    """
    if created:
        logger.info(f"New user created: {instance.email}")
        
        # Send welcome email (optional - uncomment when email is configured)
        # try:
        #     send_mail(
        #         subject='Welcome to Tactical Intelligence System',
        #         message=f'Welcome {instance.get_full_name()},\n\nYour account has been successfully created.',
        #         from_email=settings.DEFAULT_FROM_EMAIL,
        #         recipient_list=[instance.email],
        #         fail_silently=True,
        #     )
        # except Exception as e:
        #     logger.error(f"Failed to send welcome email: {str(e)}")
    else:
        logger.info(f"User updated: {instance.email}")


@receiver(pre_delete, sender=User)
def user_pre_delete(sender, instance, **kwargs):
    """
    Signal handler for when a user is deleted
    Clean up associated files (avatar)
    """
    logger.info(f"Deleting user: {instance.email}")
    
    # Delete avatar file if exists
    if instance.avatar:
        try:
            if os.path.isfile(instance.avatar.path):
                os.remove(instance.avatar.path)
                logger.info(f"Deleted avatar for user: {instance.email}")
        except Exception as e:
            logger.error(f"Error deleting avatar: {str(e)}")