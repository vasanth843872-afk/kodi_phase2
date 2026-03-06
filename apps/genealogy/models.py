from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.families.models import Family
from apps.relations.models import FixedRelation

class Person(models.Model):
    """
    Person model representing individuals in the genealogy tree.
    Can be linked to a User (registered) or be a placeholder.
    """
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )
    
    linked_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='person_record',
        db_index=True
    )
    full_name = models.CharField(max_length=200, db_index=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_death = models.DateField(null=True, blank=True)
    
    original_name = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="Original placeholder name before connection"
    )
    
    # ddddd
    is_placeholder = models.BooleanField(default=True)
    invitation_status = models.CharField(
        max_length=20,
        default='not_sent',
        choices=[
            ('not_sent', 'Not Sent'),
            ('sent', 'Invitation Sent'),
            ('accepted', 'Accepted'),
            ('declined', 'Declined')
        ]
    )
    invitation_token = models.CharField(max_length=100, blank=True)
    invited_email = models.EmailField(blank=True)
    invited_phone = models.CharField(max_length=20, blank=True)
    
    # Helper property
    @property
    def is_connected(self):
        """Check if person is connected (has user account)."""
        return bool(self.linked_user) and self.invitation_status == 'accepted'
    # ddddd
    
    # Family membership
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name='persons',
        null=True,
        blank=True,
        db_index=True
    )
    
    # Additional info
    is_alive = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'persons'
        verbose_name_plural = 'Persons'
        indexes = [
            models.Index(fields=['family', 'gender']),
            models.Index(fields=['full_name', 'family']),
            models.Index(fields=['date_of_birth']),
            models.Index(fields=['is_alive', 'is_verified']),
        ]
    
    def __str__(self):
        status = "User" if self.linked_user else "Placeholder"
        return f"{self.full_name} ({status}) - {self.family.family_name}"
    
    def clean(self):
        """Validate person data."""
        if self.date_of_birth and self.date_of_death:
            if self.date_of_death < self.date_of_birth:
                raise ValidationError("Date of death cannot be before date of birth")
        
        if self.date_of_death:
            self.is_alive = False
            
        
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_public_profile(self):
        """Get public profile if linked to a user."""
        if self.linked_user and hasattr(self.linked_user, 'profile'):
            return self.linked_user.profile.get_public_fields()
        return None
    
    def get_age(self):
        """Calculate age from date of birth."""
        if not self.date_of_birth:
            return None
        
        from datetime import date
        today = date.today()
        
        if self.date_of_death:
            reference_date = self.date_of_death
        else:
            reference_date = today
        
        age = reference_date.year - self.date_of_birth.year
        if (reference_date.month, reference_date.day) < (self.date_of_birth.month, self.date_of_birth.day):
            age -= 1
        
        return age
    
    def get_connected_persons(self, max_depth=3):
        """
        Get connected persons using BFS traversal.
        
        Args:
            max_depth: Maximum relation depth to traverse
        
        Returns:
            List of connected person IDs with depth
        """
        from collections import deque
        
        visited = {self.id: 0}
        queue = deque([(self.id, 0)])
        connected = []
        
        while queue:
            current_id, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            # Get outgoing relations
            outgoing = PersonRelation.objects.filter(
                from_person_id=current_id,
                status='confirmed'
            ).select_related('to_person')
            
            for relation in outgoing:
                if relation.to_person_id not in visited:
                    visited[relation.to_person_id] = depth + 1
                    queue.append((relation.to_person_id, depth + 1))
                    connected.append({
                        'person_id': relation.to_person_id,
                        'relation_code': relation.relation.relation_code,
                        'depth': depth + 1
                    })
            
            # Get incoming relations
            incoming = PersonRelation.objects.filter(
                to_person_id=current_id,
                status='confirmed'
            ).select_related('from_person')
            
            for relation in incoming:
                if relation.from_person_id not in visited:
                    visited[relation.from_person_id] = depth + 1
                    queue.append((relation.from_person_id, depth + 1))
                    connected.append({
                        'person_id': relation.from_person_id,
                        'relation_code': relation.relation.relation_code,
                        'depth': depth + 1,
                        'is_reverse': True
                    })
        
        return connected
    


class PersonRelation(models.Model):
    """
    Core genealogy truth - stores relationships between persons.
    This is where genealogical truth is stored ONLY ONCE.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('conflicted', 'Conflicted'),
        ('rejected', 'Rejected'),
    )
    
    from_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='outgoing_relations',
        db_index=True
    )
    to_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='incoming_relations',
        db_index=True
    )
    relation = models.ForeignKey(
        FixedRelation,
        on_delete=models.CASCADE,
        related_name='person_relations'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_relations'
    )
    
    # Conflict resolution
    conflict_reason = models.TextField(blank=True,null=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_conflicts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'person_relations'
        unique_together = ('from_person', 'to_person', 'relation')
        indexes = [
            models.Index(fields=['from_person', 'status']),
            models.Index(fields=['to_person', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['created_by', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.from_person} -> {self.to_person} ({self.relation.relation_code})"
    
    def clean(self):
        """Validate relation constraints."""
        from apps.relations.services import ConflictDetectionService
        
        # Check if persons are in the same family
        # if self.from_person.family != self.to_person.family:
        #     raise ValidationError("Persons must be in the same family")
        
        # Check gender compatibility
        from apps.relations.services import RelationLabelService
        if not RelationLabelService.validate_gender_compatibility(
            self.relation.relation_code,
            self.from_person.gender,
            self.to_person.gender
        ):
            raise ValidationError(
                f"Gender incompatible for relation {self.relation.relation_code}"
            )
            
        SINGLE_RELATIONS = {'FATHER', 'MOTHER', 'WIFE', 'HUSBAND'}

        relation_code = self.relation.relation_code

        if relation_code in SINGLE_RELATIONS:
            qs = PersonRelation.objects.filter(
                from_person=self.from_person,
                relation__relation_code=relation_code
            )

            # exclude self while updating
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            if qs.exists():
                raise ValidationError(
                    f"You already have a {relation_code.lower()}"
                )
            if relation_code in {'WIFE', 'HUSBAND'}:
                    qs = PersonRelation.objects.filter(
                        to_person=self.to_person,
                        relation__relation_code__in={'WIFE', 'HUSBAND'}
                    )

                    if self.pk:
                        qs = qs.exclude(pk=self.pk)

                    if qs.exists():
                        raise ValidationError("You already have a spouse")
            
            conflicts = []
            # Detect conflicts
            if self.status != 'conflicted':
                conflicts_result = ConflictDetectionService.detect_conflicts(
                    self.from_person_id,
                    self.to_person_id,
                    self.relation.relation_code
                )
                
                # Handle different return types
                if conflicts_result:
                    if isinstance(conflicts_result[0], dict):
                        # Extract messages from dictionaries
                        conflicts = []
                        for c in conflicts_result:
                            if isinstance(c, dict):
                                # Try common dictionary keys that might contain the message
                                message = (c.get('message') or 
                                        c.get('error') or 
                                        c.get('description') or 
                                        c.get('detail') or
                                        str(c))
                                conflicts.append(message)
                            else:
                                conflicts.append(str(c))
                    else:
                        # Already strings
                        conflicts = conflicts_result
                
                if conflicts:
                    self.status = 'conflicted'
                    self.conflict_reason = '; '.join(conflicts)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def confirm(self, confirmed_by=None):
        """Confirm a pending relation."""
        if self.status == 'pending':
            self.status = 'confirmed'
            if confirmed_by:
                self.resolved_by = confirmed_by
                self.resolved_at = timezone.now()
            self.save()
            
            # TODO: Create reciprocal relation if required
            # This is a simplification - in production, you might want to
            # automatically create reciprocal relations or handle them differently
            return True
        return False
    
    def mark_conflicted(self, reason, marked_by=None):
        """Mark relation as conflicted."""
        self.status = 'conflicted'
        self.conflict_reason = reason
        if marked_by:
            self.resolved_by = marked_by
            self.resolved_at = timezone.now()
        self.save()
    
    def get_label(self, language='en'):
        """Get relation label with context."""
        from apps.relations.services import RelationLabelService
        
        # Get context from persons
        from_profile = self.from_person.get_public_profile()
        to_profile = self.to_person.get_public_profile()
        
        # Use default values if profiles not available
        language = language or (from_profile.get('preferred_language') if from_profile else 'en')
        religion = (from_profile.get('religion') if from_profile else '') or (to_profile.get('religion') if to_profile else '')
        caste = (from_profile.get('caste') if from_profile else '') or (to_profile.get('caste') if to_profile else '')
        family_name = self.from_person.family.family_name
        
        return RelationLabelService.get_relation_label(
            relation_code=self.relation.relation_code,
            language=language,
            religion=religion,
            caste=caste,
            family_name=family_name
        )
        

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone


User = get_user_model()

# models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.relations.models import FixedRelation

User = get_user_model()

class Invitation(models.Model):
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='genealogy_invitations'
    )
    invited_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='genealogy_received_invitations'
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='genealogy_sent_invitations'
    )
    token = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('expired', 'Expired'),
            ('rejected', 'Rejected')
        ],
        default='pending'
    )
    
    # NEW FIELDS TO STORE ORIGINAL RELATION
    original_relation = models.ForeignKey(
        FixedRelation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitations',
        help_text="Original relation specified when inviting"
    )
    placeholder_gender = models.CharField(
        max_length=1,
        choices=Person.GENDER_CHOICES,
        null=True,
        blank=True,
        help_text="Gender of the placeholder at invitation time"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self):
        return self.created_at < timezone.now() - timezone.timedelta(days=7)

    def __str__(self):
        return f"Invitation to {self.invited_user} for {self.person}"
    
    class Meta:
        ordering = ['-created_at']


class AddressRelation(models.Model):
    CONTEXT_CHOICES = (
        ("ashramam", "Ashramam"),
    )

    ADDRESS_CODES = (
        ("THATHA", "THATHA"),
        ("PAATI", "PAATI"),
        ("PERIYAPPA", "PERIYAPPA"),
        ("PERIYAMMA", "PERIYAMMA"),
        ("CHITHAPPA", "CHITHAPPA"),
        ("CHITHI", "CHITHI"),
        ("MAMA", "MAMA"),
        ("ATHAN","ATHAN"),
        ("ANNI","ANNI"),
        ("KOLUNTHIYAZH", "KOLUNTHIYAZH"),
        ("ATHAI", "ATHAI"),
        ("ANNA", "ANNA"),
        ("AKKA", "AKKA"),
        ("THAMBI", "THAMBI"),
        ("THANGAI", "THANGAI"),
        ("KOLUNTHANAR", "KOLUNTHANAR"),
        ("MARUMAGAL", "MARUMAGAL"),
        ("MARUMAGAN", "MARUMAGAN"),
        ("PETTHI","PETTHI"),
        ("PERAN","PERAN"),
        ("MAITHUNAR","MAITHUNAR"),
        ("MAGHAZH","MAGHAZH"),
        ("MAGAN","MAGAN")
    )

    from_person = models.ForeignKey(
        Person, related_name="ashramam_given", on_delete=models.CASCADE
    )
    to_person = models.ForeignKey(
        Person, related_name="ashramam_received", on_delete=models.CASCADE
    )

    address_code = models.CharField(max_length=30, choices=ADDRESS_CODES)
    context = models.CharField(
        max_length=20, choices=CONTEXT_CHOICES, default="ashramam"
    )

    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("from_person", "to_person", "context")
