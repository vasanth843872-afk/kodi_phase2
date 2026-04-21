from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    """
    Central notification model for all app notifications
    """
    NOTIFICATION_TYPES = [
        # Event Notifications
        ('event_created', 'Event Created'),
        ('event_updated', 'Event Updated'),
        ('event_cancelled', 'Event Cancelled'),
        ('event_reminder', 'Event Reminder'),
        ('event_starting_soon', 'Event Starting Soon'),
        ('event_ended', 'Event Ended'),
        ('rsvp_received', 'RSVP Received'),
        ('rsvp_updated', 'RSVP Updated'),
        ('event_comment', 'Event Comment'),
        ('event_media_added', 'Event Media Added'),
        
        # Post Notifications
        ('post_created', 'Post Created'),
        ('post_updated', 'Post Updated'),
        ('post_liked', 'Post Liked'),
        ('post_commented', 'Post Commented'),
        ('post_shared', 'Post Shared'),
        ('post_mentioned', 'Mentioned in Post'),
        ('post_reported', 'Post Reported'),
        
        # Family Tree Notifications
        ('relation_added', 'New Family Member Added'),
        ('relation_confirmed', 'Relationship Confirmed'),
        ('relation_updated', 'Relationship Updated'),
        ('birth_order_updated', 'Birth Order Updated'),
        ('family_anniversary', 'Family Anniversary'),
        ('death_anniversary', 'Death Anniversary'),
        ('birthday_reminder', 'Birthday Reminder'),
        
        # System Notifications
        ('profile_update', 'Profile Update Required'),
        ('security_alert', 'Security Alert'),
        ('login_alert', 'New Login Detected'),
        ('data_export_ready', 'Data Export Ready'),
        ('backup_completed', 'Backup Completed'),
        ('system_maintenance', 'System Maintenance'),
    ]
    
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # Basic fields
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_LEVELS,
        default='medium'
    )
    
    # Read/Unread status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Generic foreign key to link to any object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional data
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Notification channels
    sent_via_websocket = models.BooleanField(default=False)
    sent_via_email = models.BooleanField(default=False)
    sent_via_sms = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['priority', 'created_at']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} for {self.user.mobile_number}: {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def is_expired(self):
        """Check if notification has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def get_icon(self):
        """Get appropriate icon for notification type"""
        icon_map = {
            'event_created': 'calendar-plus',
            'event_updated': 'calendar-edit',
            'event_cancelled': 'calendar-x',
            'event_reminder': 'bell',
            'event_starting_soon': 'clock',
            'event_ended': 'check-circle',
            'rsvp_received': 'user-check',
            'rsvp_updated': 'refresh-cw',
            'event_comment': 'message-square',
            'event_media_added': 'image',
            
            'post_created': 'file-text',
            'post_updated': 'edit',
            'post_liked': 'heart',
            'post_commented': 'message-circle',
            'post_shared': 'share',
            'post_mentioned': 'at-sign',
            'post_reported': 'flag',
            
            'relation_added': 'user-plus',
            'relation_confirmed': 'user-check',
            'relation_updated': 'edit-3',
            'birth_order_updated': 'hash',
            'family_anniversary': 'gift',
            'death_anniversary': 'heart',
            'birthday_reminder': 'cake',
            
            'profile_update': 'user',
            'security_alert': 'shield',
            'login_alert': 'log-in',
            'data_export_ready': 'download',
            'backup_completed': 'database',
            'system_maintenance': 'settings',
        }
        return icon_map.get(self.notification_type, 'bell')


class NotificationPreference(models.Model):
    """
    User notification preferences
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Channel preferences
    enable_websocket = models.BooleanField(default=True)
    enable_email = models.BooleanField(default=True)
    enable_sms = models.BooleanField(default=False)
    
    # Type preferences
    event_notifications = models.BooleanField(default=True)
    post_notifications = models.BooleanField(default=True)
    family_notifications = models.BooleanField(default=True)
    system_notifications = models.BooleanField(default=True)
    
    # Quiet hours
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    
    # Email preferences
    daily_digest = models.BooleanField(default=False)
    weekly_digest = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'notification_preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.mobile_number}"
    
    def is_quiet_hours(self):
        """Check if current time is during quiet hours"""
        if not self.quiet_hours_enabled:
            return False
        
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        current_time = timezone.now().time()
        start_time = self.quiet_hours_start
        end_time = self.quiet_hours_end
        
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        else:
            # Overnight quiet hours
            return current_time >= start_time or current_time <= end_time


class NotificationTemplate(models.Model):
    """
    Email/SMS notification templates
    """
    notification_type = models.CharField(
        max_length=50,
        unique=True
    )
    email_subject = models.CharField(max_length=200)
    email_template = models.TextField()
    sms_template = models.CharField(max_length=160)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'notification_templates'
    
    def __str__(self):
        return f"Template for {self.notification_type}"
