from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation
import json
from datetime import timedelta

# ==================== EVENT TYPE ====================

class EventType(models.Model):
    """
    Event types created by users - just a simple title
    """
    title = models.CharField(max_length=100)
    
    # Who created it
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_event_types'
    )
    
    # Which family it belongs to (if family-specific)
    family = models.ForeignKey(
        'families.Family',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='event_types'
    )
    
    # Visibility
    is_public = models.BooleanField(default=False, help_text="Visible to all users?")
    
    # Usage tracking
    usage_count = models.IntegerField(default=0)
    last_used = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'event_types'
        ordering = ['-usage_count', 'title']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['created_by']),
            models.Index(fields=['family']),
        ]
    
    def __str__(self):
        return self.title
    
    def update_usage(self):
        """Call this when event type is used"""
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


# ==================== VISIBILITY LEVELS ====================

class VisibilityLevel(models.Model):
    """
    Visibility levels (managed by admin)
    """
    VISIBILITY_CHOICES = (
        ('PUBLIC', '🌍 Public - Everyone'),
        ('CONNECTED', '👥 Connected People Only'),
        ('FAMILY', '👪 Same Family Only'),
        ('CASTE', '🕉️ Same Caste Only'),
        ('RELIGION', '⛪ Same Religion Only'),
        ('LOCATION', '📍 Same Location Only'),
        ('PRIVATE', '🔒 Only Me'),
    )
    
    code = models.CharField(max_length=50, unique=True, choices=VISIBILITY_CHOICES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Admin controls
    is_enabled = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'visibility_levels'
        ordering = ['sort_order']
    
    def __str__(self):
        return self.name


# ==================== ADMIN CONFIGURATION ====================

class EventConfig(models.Model):
    """
    Global admin configuration for events (only one record)
    """
    # Singleton
    id = models.IntegerField(primary_key=True, default=1, editable=False)
    
    # Default settings
    default_visibility = models.ForeignKey(
        VisibilityLevel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )
    allow_users_change_visibility = models.BooleanField(default=True)
    
    # Maximum visibility level users can choose
    MAX_LEVEL_CHOICES = (
        ('PUBLIC', 'Public (Least restrictive)'),
        ('CONNECTED', 'Connected Only'),
        ('FAMILY', 'Family Only'),
        ('CASTE', 'Caste Only'),
        ('RELIGION', 'Religion Only'),
        ('LOCATION', 'Location Only'),
        ('PRIVATE', 'Private (Most restrictive)'),
    )
    max_allowed_visibility = models.CharField(
        max_length=50,
        choices=MAX_LEVEL_CHOICES,
        default='PUBLIC'
    )
    
    # Auto-filters (ON/OFF)
    enable_religion_filter = models.BooleanField(default=False)
    enable_caste_filter = models.BooleanField(default=False)
    enable_family_filter = models.BooleanField(default=False)
    enable_location_filter = models.BooleanField(default=False)
    enable_connection_filter = models.BooleanField(default=True)
    
    # Restriction lists
    blocked_religions = models.JSONField(default=list, blank=True)
    blocked_castes = models.JSONField(default=list, blank=True)
    blocked_families = models.JSONField(default=list, blank=True)
    blocked_locations = models.JSONField(default=list, blank=True)
    
    # Moderation
    require_moderation = models.BooleanField(default=False)
    auto_approve_trusted_users = models.BooleanField(default=True)
    
    # Who updated
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'event_config'
    
    def save(self, *args, **kwargs):
        self.id = 1  # Force singleton
        super().save(*args, **kwargs)
        return self
    
    @classmethod
    def get_config(cls):
        """Get the singleton config"""
        config, created = cls.objects.get_or_create(id=1)
        if created and not config.default_visibility:
            # Set default visibility if none
            default = VisibilityLevel.objects.filter(code='CONNECTED').first()
            if default:
                config.default_visibility = default
                config.save()
        return config


# ==================== EVENT ====================

class Event(models.Model):
    """
    Main Event model
    """
    # Basic info
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_type = models.ForeignKey(
        EventType,
        on_delete=models.SET_NULL,
        null=True,
        related_name='events'
    )
    
    # Date & Time
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    is_all_day = models.BooleanField(default=False)
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Location
    location_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    is_virtual = models.BooleanField(default=False)
    virtual_link = models.URLField(blank=True)
    
    # Who created it
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_events'
    )
    
    # Who is this event for? (honorees)
    honorees = models.ManyToManyField(
        'genealogy.Person',
        blank=True,
        related_name='honored_in_events'
    )
    
    # ========== VISIBILITY ==========
    visibility = models.ForeignKey(
        VisibilityLevel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='events'
    )
    
    # Custom targetting
    target_religions = models.JSONField(default=list, blank=True)
    target_castes = models.JSONField(default=list, blank=True)
    target_families = models.JSONField(default=list, blank=True)
    target_locations = models.JSONField(default=list, blank=True)
    
    # Explicit invite list
    invited_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='event_invitations'
    )
    invited_persons = models.ManyToManyField(
        'genealogy.Person',
        blank=True,
        related_name='event_invitations'
    )
    
    # Exclude list
    excluded_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='excluded_from_events'
    )
    
    # ========== MODERATION ==========
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('FLAGGED', 'Flagged'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    moderation_note = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_events'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    
    # ========== MEDIA ==========
    cover_image = models.ImageField(upload_to='event_covers/%Y/%m/', null=True, blank=True,max_length=500)
    
    # ========== STATS ==========
    view_count = models.IntegerField(default=0)
    rsvp_going = models.IntegerField(default=0)
    rsvp_maybe = models.IntegerField(default=0)
    rsvp_not_going = models.IntegerField(default=0)
    
    # ========== TIMESTAMPS ==========
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'events'
        indexes = [
            models.Index(fields=['start_date', 'status']),
            models.Index(fields=['created_by', 'status']),
            models.Index(fields=['visibility', 'start_date']),
            models.Index(fields=['city', 'state']),
        ]
        ordering = ['-start_date']
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Set default visibility for new events
        if not self.pk and not self.visibility:
            config = EventConfig.get_config()
            self.visibility = config.default_visibility
        
        super().save(*args, **kwargs)
        
        # Update event type usage
        if self.event_type:
            self.event_type.update_usage()
    
    def is_visible_to(self, user):
        """
        Check if this event is visible to a specific user
        Core filtering logic
        """
        if user == self.created_by:
            return True
        # Admin can see everything
        if user.is_staff:
            return True
        if self.status == 'PENDING':
            return self._is_connected(user)
        
        # Get user profile data
        try:
            profile = user.profile
            person = user.person_record
        except:
            return False
        
        # Check explicit exclusion
        if self.excluded_users.filter(id=user.id).exists():
            return False
        
        # Check explicit invitation
        if self.invited_users.filter(id=user.id).exists():
            return True
        if person and self.invited_persons.filter(id=person.id).exists():
            return True
        
        # Check visibility level
        if not self.visibility:
            return False
        
        config = EventConfig.get_config()
        
        # Apply global filters first
        if not self._passes_global_filters(profile, config):
            return False
        
        # Check specific visibility level
        return self._check_visibility_level(user, profile, person, config)
    
    def _passes_global_filters(self, profile, config):
        """Check if user passes global filters"""
        
        # Religion filter
        if config.blocked_religions and profile.religion in config.blocked_religions:
            return False
        
        # Caste filter
        if config.blocked_castes and profile.caste in config.blocked_castes:
            return False
        
        # Family filter
        if config.blocked_families and profile.familyname1 in config.blocked_families:
            return False
        
        return True
    
    def _check_visibility_level(self, user, profile, person, config):
        """Check specific visibility level"""
        
        code = self.visibility.code
        
        # PUBLIC - everyone
        if code == 'PUBLIC':
            return True
        
        # PRIVATE - only creator
        if code == 'PRIVATE':
            return self.created_by == user
        
        # CONNECTED - check connection
        if code == 'CONNECTED':
            if not config.enable_connection_filter:
                return True
            return self._is_connected(user, person)
        
        # FAMILY - same family
        if code == 'FAMILY':
            if not config.enable_family_filter:
                return True
            return self._same_family(profile)
        
        # CASTE - same caste
        if code == 'CASTE':
            if not config.enable_caste_filter:
                return True
            return self._same_caste(profile)
        
        # RELIGION - same religion
        if code == 'RELIGION':
            if not config.enable_religion_filter:
                return True
            return self._same_religion(profile)
        
        # LOCATION - same location
        if code == 'LOCATION':
            if not config.enable_location_filter:
                return True
            return self._same_location(profile)
        
        return False
    
    def _is_connected(self, user, person):
        """Check if user is connected to event creator"""
        if not person:
            return False
        
        from apps.genealogy.models import PersonRelation
        creator_person = getattr(self.created_by, 'person_record', None)
        
        if not creator_person:
            return False
        
        return PersonRelation.objects.filter(
            models.Q(from_person=person, to_person=creator_person) |
            models.Q(from_person=creator_person, to_person=person),
            status='confirmed'
        ).exists()
    
    def _same_family(self, profile):
        """Check if user has same family as target"""
        if not self.target_families:
            return True
        return profile.familyname1 in self.target_families
    
    def _same_caste(self, profile):
        """Check if user has same caste as target"""
        if not self.target_castes:
            return True
        return profile.caste in self.target_castes
    
    def _same_religion(self, profile):
        """Check if user has same religion as target"""
        if not self.target_religions:
            return True
        return profile.religion in self.target_religions
    
    def _same_location(self, profile):
        """Check if user has same location as target"""
        if not self.target_locations:
            return True
        return profile.present_city in self.target_locations


# ==================== RSVP ====================

class RSVP(models.Model):
    """
    RSVP tracking for events
    """
    RESPONSE_CHOICES = (
        ('GOING', '✅ Going'),
        ('MAYBE', '🤔 Maybe'),
        ('NOT_GOING', '❌ Not Going'),
    )
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='rsvps')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_rsvps')
    
    response = models.CharField(max_length=20, choices=RESPONSE_CHOICES, default='GOING')
    guests_count = models.IntegerField(default=0)
    guest_names = models.TextField(blank=True, help_text="Names of additional guests")
    dietary_restrictions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'event_rsvps'
        unique_together = ['event', 'user']
        indexes = [
            models.Index(fields=['event', 'response']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.response}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._update_event_counts()
    
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._update_event_counts()
    
    def _update_event_counts(self):
        """Update event RSVP counts"""
        event = self.event
        event.rsvp_going = event.rsvps.filter(response='GOING').count()
        event.rsvp_maybe = event.rsvps.filter(response='MAYBE').count()
        event.rsvp_not_going = event.rsvps.filter(response='NOT_GOING').count()
        event.save(update_fields=['rsvp_going', 'rsvp_maybe', 'rsvp_not_going'])


# ==================== EVENT MEDIA ====================

class EventMedia(models.Model):
    """
    Photos and videos from events
    """
    MEDIA_TYPES = (
        ('PHOTO', 'Photo'),
        ('VIDEO', 'Video'),
    )
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='media')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    file = models.FileField(upload_to='event_media/%Y/%m/')
    thumbnail = models.ImageField(upload_to='event_thumbnails/', null=True, blank=True)
    
    caption = models.TextField(blank=True)
    
    # Tagged people
    tagged_persons = models.ManyToManyField(
        'genealogy.Person',
        blank=True,
        related_name='tagged_in_media'
    )
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'event_media'
        ordering = ['-uploaded_at']


# ==================== EVENT COMMENTS ====================

class EventComment(models.Model):
    """
    Comments on events
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    content = models.TextField()
    
    # Moderation
    is_approved = models.BooleanField(default=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'event_comments'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.user.username}"


# ==================== EVENT FLAGS ====================

class EventFlag(models.Model):
    """
    User reports for inappropriate events
    """
    REASON_CHOICES = (
        ('INAPPROPRIATE', 'Inappropriate content'),
        ('SPAM', 'Spam'),
        ('WRONG_VISIBILITY', 'Wrong visibility settings'),
        ('HARASSMENT', 'Harassment'),
        ('FAKE', 'Fake event'),
        ('OTHER', 'Other'),
    )
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='flags')
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    description = models.TextField(blank=True)
    
    # Status
    STATUS_CHOICES = (
        ('PENDING', 'Pending Review'),
        ('RESOLVED', 'Resolved'),
        ('DISMISSED', 'Dismissed'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_flags'
    )
    resolution_note = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'event_flags'
        unique_together = ['event', 'reported_by']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]


# ==================== USER RESTRICTIONS ====================

class UserRestriction(models.Model):
    """
    Individual user restrictions (set by admin)
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='event_restrictions'
    )
    
    # Can they create events?
    can_create_events = models.BooleanField(default=True)
    
    # Override max visibility
    max_visibility = models.CharField(
        max_length=50,
        choices=VisibilityLevel.VISIBILITY_CHOICES,
        null=True,
        blank=True
    )
    
    # Restricted to specific visibility only
    restricted_to_visibility = models.ManyToManyField(
        VisibilityLevel,
        blank=True,
        related_name='restricted_users'
    )
    
    # Block lists
    blocked_religions = models.JSONField(default=list, blank=True)
    blocked_castes = models.JSONField(default=list, blank=True)
    blocked_families = models.JSONField(default=list, blank=True)
    
    # Reason
    restriction_reason = models.TextField(blank=True)
    
    # Who set this
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='imposed_restrictions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_restrictions'
    
    def __str__(self):
        return f"Restrictions for {self.user.username}"