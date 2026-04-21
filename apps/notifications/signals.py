from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import NotificationPreference
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Create notification preferences for new users"""
    if created:
        NotificationPreference.objects.get_or_create(user=instance)
        logger.info(f"Created notification preferences for user {instance.id}")
