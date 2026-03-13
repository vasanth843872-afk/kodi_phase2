from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Event, RSVP, EventComment, EventFlag

@receiver(post_save, sender=RSVP)
@receiver(post_delete, sender=RSVP)
def update_event_rsvp_counts(sender, instance, **kwargs):
    """Update event RSVP counts when RSVP changes"""
    event = instance.event
    event.rsvp_going = event.rsvps.filter(response='GOING').count()
    event.rsvp_maybe = event.rsvps.filter(response='MAYBE').count()
    event.rsvp_not_going = event.rsvps.filter(response='NOT_GOING').count()
    event.save(update_fields=['rsvp_going', 'rsvp_maybe', 'rsvp_not_going'])


@receiver(post_save, sender=EventFlag)
def handle_event_flag(sender, instance, created, **kwargs):
    """Mark event as flagged when first flag is created"""
    if created:
        event = instance.event
        if event.status == 'APPROVED':
            event.status = 'FLAGGED'
            event.save(update_fields=['status'])