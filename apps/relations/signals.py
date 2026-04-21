# apps/relations/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import FixedRelation
from .services import clear_relation_caches

@receiver(post_save, sender=FixedRelation)
@receiver(post_delete, sender=FixedRelation)
def auto_clear_relation_caches(sender, instance, **kwargs):
    """
    Automatically clear all relation-related caches whenever a
    FixedRelation is created, updated, or deleted.
    """
    clear_relation_caches()