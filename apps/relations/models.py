from django.db import models

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
    category = models.CharField(max_length=50, choices=RELATION_CATEGORIES)
    is_active = models.BooleanField(default=True, help_text="Whether this relation is currently active/available")
    
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
    
    def get_localized_name(self, language='en', religion='', caste='', family=''):
        """
        Get relation name with localization hierarchy:
        1. Family-specific (highest priority)
        2. Caste-specific
        3. Language+Religion specific
        4. FixedRelation defaults (lowest priority)
        """
        # Level 1: Family-specific
        if family:
            family_label = self.family_labels.filter(
                language=language,
                religion=religion,
                caste=caste,
                family=family
            ).first()
            if family_label:
                return family_label.label
        
        # Level 2: Caste-specific
        if caste:
            caste_label = self.caste_labels.filter(
                language=language,
                religion=religion,
                caste=caste
            ).first()
            if caste_label:
                return caste_label.label
        
        # Level 3: Language+Religion specific
        if religion:
            lang_rel_label = self.language_religion_labels.filter(
                language=language,
                religion=religion
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

class RelationLanguageReligion(models.Model):
    """
    Level 3: Language + Religion specific labels.
    Falls back to FixedRelation defaults.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='language_religion_labels')
    language = models.CharField(max_length=50, db_index=True)
    religion = models.CharField(max_length=100, db_index=True)
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_language_religion'
        unique_together = ('relation', 'language', 'religion')
        indexes = [
            models.Index(fields=['language', 'religion']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.language}/{self.religion}: {self.label}"

class RelationCaste(models.Model):
    """
    Level 2: Language + Religion + Caste specific labels.
    Overrides Level 3.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='caste_labels')
    language = models.CharField(max_length=50, db_index=True)
    religion = models.CharField(max_length=100, db_index=True)
    caste = models.CharField(max_length=100, db_index=True)
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_caste'
        unique_together = ('relation', 'language', 'religion', 'caste')
        indexes = [
            models.Index(fields=['language', 'religion', 'caste']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.language}/{self.religion}/{self.caste}: {self.label}"

class RelationFamily(models.Model):
    """
    Level 1: Family-specific overrides.
    Highest priority - overrides all other levels.
    """
    relation = models.ForeignKey(FixedRelation, on_delete=models.CASCADE, related_name='family_labels')
    language = models.CharField(max_length=50, db_index=True)
    religion = models.CharField(max_length=100, db_index=True)
    caste = models.CharField(max_length=100, db_index=True)
    family = models.CharField(max_length=200, db_index=True, help_text="Family name or identifier")
    label = models.CharField(max_length=200)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'relation_family'
        unique_together = ('relation', 'language', 'religion', 'caste', 'family')
        indexes = [
            models.Index(fields=['family', 'language']),
        ]
    
    def __str__(self):
        return f"{self.relation.relation_code} - {self.family}: {self.label}"
    
    

class RelationProfileOverride(models.Model):
    """
    Complete override model that includes ALL profile fields:
    - Basic: language, religion, caste, family
    - Location: native, present_city, taluk, district, state, nationality
    """
    relation = models.ForeignKey(
        FixedRelation,
        on_delete=models.CASCADE,
        related_name='profile_overrides'
    )
    
    # Basic fields (from existing overrides)
    language = models.CharField(max_length=10, choices=[('en', 'English'), ('ta', 'Tamil')], default='en')
    religion = models.CharField(max_length=100, blank=True, null=True)
    caste = models.CharField(max_length=100, blank=True, null=True)
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
            models.Index(fields=['relation', 'language', 'religion']),
            models.Index(fields=['relation', 'language', 'religion', 'caste']),
            models.Index(fields=['relation', 'language', 'religion', 'caste', 'family']),
            
            # Location combinations
            models.Index(fields=['relation', 'native', 'present_city']),
            models.Index(fields=['relation', 'district', 'state']),
            models.Index(fields=['relation', 'nationality']),
            models.Index(fields=['relation', 'state', 'district', 'taluk']),
            
            # Mixed combinations
            models.Index(fields=['relation', 'religion', 'state']),
            models.Index(fields=['relation', 'caste', 'district']),
        ]
        # Unique constraint on all fields to prevent duplicates
        unique_together = [
            ['relation', 'language', 'religion', 'caste', 'family', 
             'native', 'present_city', 'taluk', 'district', 'state', 'nationality']
        ]
    
    def __str__(self):
        parts = [f"{self.relation.relation_code}"]
        
        if self.religion:
            parts.append(f"religion={self.religion}")
        if self.caste:
            parts.append(f"caste={self.caste}")
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
        if self.religion: fields.append('religion')
        if self.caste: fields.append('caste')
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
    #         self.family, self.caste, self.religion,
    #         self.native, self.present_city, self.taluk,
    #         self.district, self.state, self.nationality
    #     ]
    #     return sum(1 for field in fields if field)