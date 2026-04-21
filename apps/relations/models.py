from django.db import models
from django.db.models import Q
from django.conf import settings

class FixedRelation(models.Model):
    """
    Core relation codes that define genealogical truth.
    These are immutable system-defined relationships.
    """
    RELATION_CATEGORIES = (
        ('PARENT', 'Parent'),
        ('CHILD', 'Child'),
        ('SPOUSE', 'Spouse'),
        ('SIBLING', 'Sibling'),
        ('GRANDPARENT', 'Grandparent'),
        ('GRANDCHILD', 'Grandchild'),
        ('OTHER', 'Other'),
    )
    
    relation_code = models.CharField(max_length=50, unique=True, db_index=True)
    default_english = models.CharField(max_length=100)
    default_tamil = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=RELATION_CATEGORIES,blank=True,null=True)
    is_active = models.BooleanField(default=True, help_text="Whether this relation is currently active/available")
    composition_token = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional token used for path composition. If blank, derived from default_english."
    )
    match_token = models.CharField(
        max_length=100,
        blank=True,
        help_text="Token used to match composed paths. If blank, derived from default_english."
    )
    
    # Gender restrictions (optional)
    from_gender = models.CharField(max_length=1, choices=[
        ('M', 'Male'),
        ('F', 'Female'),
        ('A', 'Any')
    ], default='A')
    to_gender = models.CharField(max_length=1, choices=[
        ('M', 'Male'),
        ('F', 'Female'),
        ('A', 'Any')
    ], default='A')
    
    # Biological constraints
    max_instances = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    is_reciprocal_required = models.BooleanField(default=True)
    
    # Custom relation flag
    is_custom = models.BooleanField(default=False, help_text="Whether this is a user-defined custom relation")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'fixed_relations'
        indexes = [
            models.Index(fields=['relation_code', 'category']),
        ]
    
    def __str__(self):
        return f"{self.relation_code} ({self.default_english})"
    
    def get_reciprocal(self):
        """
        Get reciprocal relation code.
        This should be defined as a separate FixedRelation entry.
        """
        reciprocal_map = {
            'FATHER': 'SON', 'MOTHER': 'DAUGHTER',
            'SON': 'FATHER', 'DAUGHTER': 'MOTHER',
            'HUSBAND': 'WIFE', 'WIFE': 'HUSBAND',
            'BROTHER': 'BROTHER', 'SISTER': 'SISTER',
            'GRANDFATHER': 'GRANDSON', 'GRANDMOTHER': 'GRANDDAUGHTER',
        }
        return reciprocal_map.get(self.relation_code)
    
    def get_localized_name(self, language='en', lifestyle='', familyname8='', family=''):
        """
        Get relation name with localization hierarchy:
        1. Family-specific (highest priority)
        2. familyname8-specific
        3. Language+lifestyle specific
        4. FixedRelation defaults (lowest priority)
        """
        # Level 1: Family-specific
        if family:
            family_label = self.family_labels.filter(
                language=language,
                lifestyle=lifestyle,
                familyname8=familyname8,
                family=family
            ).first()
            if family_label:
                return family_label.label
        
        # Level 2: familyname8-specific
        if familyname8:
            familyname8_label = self.familyname8_labels.filter(
                language=language,
                lifestyle=lifestyle,
                familyname8=familyname8
            ).first()
            if familyname8_label:
                return familyname8_label.label
        
        # Level 3: Language+lifestyle specific
        if lifestyle:
            lang_rel_label = self.language_lifestyle_labels.filter(
                language=language,
                lifestyle=lifestyle
            ).first()
            if lang_rel_label:
                return lang_rel_label.label
        
        # Level 4: Defaults
        if language == 'ta' and self.default_tamil:
            return self.default_tamil
        elif language == 'en' and self.default_english:
            return self.default_english
        
        # Fallback
        return self.default_english or self.relation_code

class RelationLanguagelifestyle(models.Model):
    """
    Level 3: Language + lifestyle specific labels.
    Falls back to FixedRelation defaults.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='language_lifestyle_labels')
    language = models.CharField(max_length=50, db_index=True)
    lifestyle = models.CharField(max_length=100, db_index=True)
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_language_lifestyle'
        unique_together = ('relation', 'language', 'lifestyle')
        indexes = [
            models.Index(fields=['language', 'lifestyle']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.language}/{self.lifestyle}: {self.label}"

class Relationfamilyname8(models.Model):
    """
    Level 2: Language + lifestyle + familyname8 specific labels.
    Overrides Level 3.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='familyname8_labels')
    language = models.CharField(max_length=50, db_index=True)
    lifestyle = models.CharField(max_length=100, db_index=True)
    familyname8 = models.CharField(max_length=100, db_index=True)
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_familyname8'
        unique_together = ('relation', 'language', 'lifestyle', 'familyname8')
        indexes = [
            models.Index(fields=['language', 'lifestyle', 'familyname8']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.language}/{self.lifestyle}/{self.familyname8}: {self.label}"

class RelationFamily(models.Model):
    """
    Level 1: Family-specific overrides.
    Highest priority - overrides all other levels.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='family_labels')
    language = models.CharField(max_length=50, db_index=True)
    lifestyle = models.CharField(max_length=100, db_index=True)
    familyname8 = models.CharField(max_length=100, db_index=True)
    family = models.CharField(max_length=200, db_index=True, help_text="Family name or identifier")
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_family'
        unique_together = ('relation', 'language', 'lifestyle', 'familyname8', 'family')
        indexes = [
            models.Index(fields=['family', 'language']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.family}: {self.label}"
    
    

class RelationProfileOverride(models.Model):
    """
    Complete override model that includes ALL profile fields:
    - Basic: language, lifestyle, familyname8, family
    - Location: native, present_city, taluk, district, state, nationality
    """
    relation = models.ForeignKey(
        FixedRelation,
        on_delete=models.CASCADE,
        related_name='profile_overrides'
    )
    
    # Basic fields (from existing overrides)
    language = models.CharField(max_length=10, choices=[('en', 'English'), ('ta', 'Tamil')], default='en')
    lifestyle = models.CharField(max_length=100, blank=True, null=True)
    familyname8 = models.CharField(max_length=100, blank=True, null=True)
    family = models.CharField(max_length=200, blank=True, null=True)
    
    # Profile location fields (NEW)
    native = models.CharField(max_length=200, blank=True, null=True)
    present_city = models.CharField(max_length=100, blank=True, null=True)
    taluk = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    nationality = models.CharField(max_length=100, blank=True, null=True)
    
    # The override label
    label = models.CharField(max_length=200)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    class Meta:
        db_table = 'relation_profile_overrides'
        indexes = [
            # Basic combinations
            models.Index(fields=['relation', 'language', 'lifestyle']),
            models.Index(fields=['relation', 'language', 'lifestyle', 'familyname8']),
            models.Index(fields=['relation', 'language', 'lifestyle', 'familyname8', 'family']),
            
            # Location combinations
            models.Index(fields=['relation', 'native', 'present_city']),
            models.Index(fields=['relation', 'district', 'state']),
            models.Index(fields=['relation', 'nationality']),
            models.Index(fields=['relation', 'state', 'district', 'taluk']),
            
            # Mixed combinations
            models.Index(fields=['relation', 'lifestyle', 'state']),
            models.Index(fields=['relation', 'familyname8', 'district']),
        ]
        # Unique constraint on all fields to prevent duplicates
        unique_together = [
            ['relation', 'language', 'lifestyle', 'familyname8', 'family', 
             'native', 'present_city', 'taluk', 'district', 'state', 'nationality']
        ]
    
    def __str__(self):
        parts = [f"{self.relation.relation_code}"]
        
        if self.lifestyle:
            parts.append(f"lifestyle={self.lifestyle}")
        if self.familyname8:
            parts.append(f"familyname8={self.familyname8}")
        if self.family:
            parts.append(f"family={self.family}")
        if self.native:
            parts.append(f"native={self.native}")
        if self.present_city:
            parts.append(f"city={self.present_city}")
        if self.taluk:
            parts.append(f"taluk={self.taluk}")
        if self.district:
            parts.append(f"district={self.district}")
        if self.state:
            parts.append(f"state={self.state}")
        if self.nationality:
            parts.append(f"nationality={self.nationality}")
        
        return f"{' - '.join(parts)} -> {self.label}"
    
    
    def get_non_empty_fields(self):
        """Return list of fields that have non-empty values."""
        fields = []
        if self.language: fields.append('language')
        if self.lifestyle: fields.append('lifestyle')
        if self.familyname8: fields.append('familyname8')
        if self.family: fields.append('family')
        if self.native: fields.append('native')
        if self.present_city: fields.append('present_city')
        if self.taluk: fields.append('taluk')
        if self.district: fields.append('district')
        if self.state: fields.append('state')
        if self.nationality: fields.append('nationality')
        return fields
    
    def get_specificity_score(self):
        """Return number of non-empty fields (higher = more specific)."""
        return len(self.get_non_empty_fields())
    
    # def get_specificity_score(self):
    #     """Calculate how specific this override is (higher = more specific)."""
    #     fields = [
    #         self.family, self.familyname8, self.lifestyle,
    #         self.native, self.present_city, self.taluk,
    #         self.district, self.state, self.nationality
    #     ]
    #     return sum(1 for field in fields if field)


class UserConnection(models.Model):
    """Model for managing user connections (friendships/follows)."""
    
    CONNECTION_TYPES = [
        ('family', 'Family'),
        ('friend', 'Friend'),
        ('colleague', 'Colleague'),
        ('community', 'Community'),
        ('other', 'Other'),
    ]
    
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='connections_initiated'
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='connections_received'
    )
    connection_type = models.CharField(
        max_length=20,
        choices=CONNECTION_TYPES,
        default='friend'
    )
    is_active = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)
    
    # Who initiated the connection request
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='connection_requests_made'
    )
    
    # When the connection was established
    established_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_connections'
        unique_together = ('user1', 'user2')
        indexes = [
            models.Index(fields=['user1', 'is_active']),
            models.Index(fields=['user2', 'is_active']),
            models.Index(fields=['is_active', 'established_at']),
        ]
    
    def __str__(self):
        return f"{self.user1.mobile_number} {self.user2.mobile_number} ({self.connection_type})"
    
    @classmethod
    def are_users_connected(cls, user1, user2):
        """Check if two users are connected."""
        return cls.objects.filter(
            Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1),
            is_active=True,
            is_blocked=False
        ).exists()
    
    @classmethod
    def get_user_connections(cls, user):
        """Get all active connections for a user."""
        return cls.objects.filter(
            Q(user1=user) | Q(user2=user),
            is_active=True,
            is_blocked=False
        ).select_related('user1', 'user2')