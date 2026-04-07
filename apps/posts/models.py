from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import json


class Post(models.Model):
    """Main Post model with advanced visibility system."""
    
    VISIBILITY_TYPES = [
        ('public', 'Public'),
        ('connections', 'Connections'),
        ('private', 'Private'),
        ('custom', 'Custom'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts'
    )
    content = models.TextField()
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_TYPES,
        default='connections'
    )
    
    # Custom visibility rule reference
    custom_visibility_rule = models.ForeignKey(
        'PostVisibilityRule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts'
    )
    
    # Engagement tracking
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
    
    # Status fields
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    is_reported = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'posts'
        indexes = [
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['visibility', 'is_active', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active', 'is_deleted']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Post by {self.author.mobile_number}: {self.content[:50]}"
    
    def get_visible_to_user(self, user):
        """Check if post is visible to specific user."""
        if self.is_deleted or not self.is_active:
            return False
        
        # Author can always see their own posts
        if self.author == user:
            return True
        
        # Public posts are visible to everyone
        if self.visibility == 'public':
            return True
        
        # Private posts only visible to author
        if self.visibility == 'private':
            return False
        
        # Connection posts - check if users are connected
        if self.visibility == 'connections':
            return self._are_users_connected(user)
        
        # Custom visibility - check rules
        if self.visibility == 'custom':
            return self._check_custom_visibility(user)
        
        return False
    
    def _are_users_connected(self, user):
        """Check if two users are connected."""
        from apps.relations.models import UserConnection
        return UserConnection.are_users_connected(self.author, user)
    
    def _check_custom_visibility(self, user):
        """Check if user meets custom visibility criteria."""
        if not self.custom_visibility_rule:
            return False
        
        return self.custom_visibility_rule.is_user_eligible(user)
    
    def update_engagement_counts(self):
        """Update engagement counters efficiently."""
        self.likes_count = self.likes.filter(is_active=True).count()
        self.comments_count = self.comments.filter(is_deleted=False).count()
        self.shares_count = self.shares.filter(is_active=True).count()
        self.save(update_fields=['likes_count', 'comments_count', 'shares_count'])


class PostVisibilityRule(models.Model):
    """Admin-defined visibility rules for posts."""
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=200, help_text="Rule name for admin reference")
    description = models.TextField(blank=True)
    
    # Rule criteria - JSON fields for flexible filtering
    caste_criteria = models.JSONField(
        default=list,
        blank=True,
        help_text="List of caste values (OR logic within field)"
    )
    religion_criteria = models.JSONField(
        default=list,
        blank=True,
        help_text="List of religion values (OR logic within field)"
    )
    family_name_criteria = models.JSONField(
        default=list,
        blank=True,
        help_text="List of family name values (OR logic within field)"
    )
    area_criteria = models.JSONField(
        default=list,
        blank=True,
        help_text="List of area values (present_city, district, state)"
    )
    
    # Rule status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_visibility_rules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'post_visibility_rules'
        indexes = [
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Visibility Rule: {self.name}"
    
    def is_user_eligible(self, user):
        """Check if user meets all rule criteria (AND logic between fields)."""
        if not self.is_active:
            return False
        
        try:
            profile = user.profile
        except AttributeError:
            return False
        
        # Check each criterion - ALL must match (AND logic)
        if self.caste_criteria and profile.caste not in self.caste_criteria:
            return False
        
        if self.religion_criteria and profile.religion not in self.religion_criteria:
            return False
        
        # Check family names across all family name fields
        if self.family_name_criteria:
            family_names = [
                profile.familyname1, profile.familyname2, profile.familyname3,
                profile.familyname4, profile.familyname5
            ]
            if not any(name in self.family_name_criteria for name in family_names if name):
                return False
        
        # Check area criteria across location fields
        if self.area_criteria:
            areas = [profile.present_city, profile.district, profile.state]
            if not any(area in self.area_criteria for area in areas if area):
                return False
        
        return True
    
    def get_eligible_users_queryset(self):
        """Get queryset of eligible users for this rule."""
        from apps.profiles.models import UserProfile
        
        queryset = UserProfile.objects.all()
        
        if self.caste_criteria:
            queryset = queryset.filter(caste__in=self.caste_criteria)
        
        if self.religion_criteria:
            queryset = queryset.filter(religion__in=self.religion_criteria)
        
        if self.family_name_criteria:
            queryset = queryset.filter(
                Q(familyname1__in=self.family_name_criteria) |
                Q(familyname2__in=self.family_name_criteria) |
                Q(familyname3__in=self.family_name_criteria) |
                Q(familyname4__in=self.family_name_criteria) |
                Q(familyname5__in=self.family_name_criteria)
            )
        
        if self.area_criteria:
            queryset = queryset.filter(
                Q(present_city__in=self.area_criteria) |
                Q(district__in=self.area_criteria) |
                Q(state__in=self.area_criteria)
            )
        
        return queryset


class PostMedia(models.Model):
    """Media attachments for posts."""
    
    MEDIA_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
    ]
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='media'
    )
    file = models.FileField(
        upload_to='post_media/%Y/%m/%d/',
        max_length=500
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100)
    
    # Optional metadata
    caption = models.TextField(blank=True)
    thumbnail = models.ImageField(
        upload_to='post_thumbnails/%Y/%m/%d/',
        null=True,
        blank=True,
        max_length=500
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_media'
        indexes = [
            models.Index(fields=['post', 'media_type']),
        ]
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.media_type} for Post {self.post.id}"


class PostLike(models.Model):
    """Post likes model."""
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='liked_posts'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_likes'
        unique_together = ('post', 'user')
        indexes = [
            models.Index(fields=['post', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.mobile_number} likes Post {self.post.id}"


class PostComment(models.Model):
    """Post comments model."""
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    content = models.TextField()
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    # Status fields
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'post_comments'
        indexes = [
            models.Index(fields=['post', 'is_deleted', 'created_at']),
            models.Index(fields=['author', 'created_at']),
            models.Index(fields=['parent', 'created_at']),
        ]
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.author.mobile_number} on Post {self.post.id}"
    
    def get_replies_count(self):
        """Get count of active replies."""
        return self.replies.filter(is_deleted=False).count()


class PostShare(models.Model):
    """Post shares model."""
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='shares'
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shared_posts'
    )
    
    # Share context
    share_text = models.TextField(blank=True)
    share_platform = models.CharField(
        max_length=50,
        choices=[
            ('internal', 'Internal Share'),
            ('external', 'External Platform'),
        ],
        default='internal'
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_shares'
        indexes = [
            models.Index(fields=['post', 'is_active']),
            models.Index(fields=['shared_by', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.shared_by.mobile_number} shared Post {self.post.id}"


class PostSave(models.Model):
    """Post bookmarks/saves model."""
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='saves'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_posts'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_saves'
        unique_together = ('post', 'user')
        indexes = [
            models.Index(fields=['user', 'is_active', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.mobile_number} saved Post {self.post.id}"


class PostReport(models.Model):
    """Post reports model for moderation."""
    
    REPORT_REASONS = [
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('harassment', 'Harassment'),
        ('misinformation', 'Misinformation'),
        ('violence', 'Violence'),
        ('copyright', 'Copyright Violation'),
        ('other', 'Other'),
    ]
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_made'
    )
    reason = models.CharField(max_length=50, choices=REPORT_REASONS)
    description = models.TextField(blank=True)
    
    # Admin action fields
    is_reviewed = models.BooleanField(default=False)
    is_action_taken = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_reports'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_reports'
        unique_together = ('post', 'reported_by')
        indexes = [
            models.Index(fields=['post', 'is_reviewed']),
            models.Index(fields=['reason', 'is_reviewed']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Post {self.post.id} reported for {self.reason}"


class PostAudience(models.Model):
    """Precomputed audience table for performance optimization."""
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='precomputed_audience'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='visible_posts'
    )
    
    # Cache the visibility reason for debugging/analytics
    visibility_reason = models.CharField(
        max_length=50,
        choices=[
            ('author', 'Author'),
            ('public', 'Public'),
            ('connection', 'Connection'),
            ('custom_rule', 'Custom Rule'),
        ]
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'post_audience'
        unique_together = ('post', 'user')
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['post', 'visibility_reason']),
        ]
    
    def __str__(self):
        return f"Post {self.post.id} visible to {self.user.mobile_number}"
