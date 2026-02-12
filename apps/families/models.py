from django.db import models
from django.conf import settings

class Family(models.Model):
    """Family model for grouping related persons."""
    
    family_name = models.CharField(max_length=200, db_index=True,null=True,blank=True,default="My family")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_families'
    )
    is_locked = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'families'
        verbose_name_plural = 'Families'
        indexes = [
            models.Index(fields=['family_name']),
            models.Index(fields=['created_by', 'created_at']),
        ]
    
    def __str__(self):
        return self.family_name
    
    def get_members_count(self):
        """Return count of persons in this family."""
        return self.persons.count()
    
    def get_active_members(self):
        """Return active user members."""
        from apps.genealogy.models import Person
        return Person.objects.filter(
            family=self,
            linked_user__isnull=False,
            linked_user__is_active=True
        ).select_related('linked_user')
        
    @property
    def display_name(self):
        """Smart display name."""
        if self.family_name and self.family_name.strip():
            return self.family_name.strip()
        
        # Default to creator's name
        if self.created_by and hasattr(self.created_by, 'profile'):
            if self.created_by.profile.firstname:
                return f"{self.created_by.profile.firstname}'s Family"
        
        return f"Family of {self.created_by.mobile_number}"

class FamilyInvitation(models.Model):
    """Track family invitations."""
    
    INVITATION_STATUS = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired')
    )
    
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='invitations')
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_invitations'
    )
    invitee_mobile = models.CharField(max_length=15, db_index=True)
    invitee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_invitations'
    )
    status = models.CharField(max_length=20, choices=INVITATION_STATUS, default='pending')
    invitation_token = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'family_invitations'
        indexes = [
            models.Index(fields=['invitee_mobile', 'status']),
            models.Index(fields=['invitation_token']),
            models.Index(fields=['expires_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.family.family_name} - {self.invitee_mobile}"
    
    def is_expired(self):
        """Check if invitation is expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at
    
    def accept(self, user=None):
        """Accept the invitation."""
        if self.is_expired():
            self.status = 'expired'
            self.save()
            return False
        
        self.status = 'accepted'
        if user:
            self.invitee_user = user
        self.save()
        return True
    
    def reject(self):
        """Reject the invitation."""
        self.status = 'rejected'
        self.save()