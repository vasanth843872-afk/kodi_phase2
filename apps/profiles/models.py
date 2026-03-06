from django.db import models
from django.conf import settings

class UserProfile(models.Model):
    """User profile with 3-step privacy levels."""
    
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ta', 'Tamil'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True
    )
    
    # STEP-1: PUBLIC FIELDS (Visible to all connected users)
    firstname = models.CharField(max_length=100, blank=True)
    secondname = models.CharField(max_length=100, blank=True)
    thirdname = models.CharField(max_length=100, blank=True)
    image=models.ImageField(upload_to='images/',null=True,blank=True)
    fathername1 = models.CharField(max_length=100, blank=True)
    fathername2 = models.CharField(max_length=100, blank=True)
    mothername1 = models.CharField(max_length=100, blank=True)
    mothername2 = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=[
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other')
    ], blank=True)
    
    # STEP-2: NEVER PUBLISHED (Private to user only)
    dateofbirth = models.DateField(null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    native = models.CharField(max_length=200, blank=True)
    present_city = models.CharField(max_length=100, blank=True)
    taluk = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    contact_number = models.CharField(max_length=15, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    
    # STEP-3: NEVER PUBLISHED (Private to user only)
    cultureoflife = models.TextField(blank=True)
    familyname1 = models.CharField(max_length=100, blank=True)
    familyname2 = models.CharField(max_length=100, blank=True)
    familyname3 = models.CharField(max_length=100, blank=True)
    familyname4 = models.CharField(max_length=100, blank=True)
    familyname5 = models.CharField(max_length=100, blank=True)
    
    # Additional fields
    preferred_language = models.CharField(max_length=50, default='en',choices=LANGUAGE_CHOICES,)
    religion = models.CharField(max_length=100, blank=True)
    caste = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        indexes = [
            models.Index(fields=['user', 'gender']),
            models.Index(fields=['religion', 'caste']),
        ]
    
    def __str__(self):
        return f"{self.user.mobile_number} - Profile"
    
    def get_public_fields(self):
        """Return only STEP-1 public fields."""
        return {
            'firstname': self.firstname,
            'secondname': self.secondname,
            'thirdname': self.thirdname,
            'fathername1': self.fathername1,
            'fathername2': self.fathername2,
            'mothername1': self.mothername1,
            'mothername2': self.mothername2,
            'image': self.image.url if self.image else None,
            'gender': self.gender,
            'preferred_language': self.preferred_language,
            
        }
    
    def get_private_fields(self):
        """Return all fields for owner only."""
        return {
            **self.get_public_fields(),
            'dateofbirth': self.dateofbirth,
            'age': self.age,
            'native': self.native,
            'present_city': self.present_city,
            'taluk': self.taluk,
            'district': self.district,
            'state': self.state,
            'contact_number': self.contact_number,
            'nationality': self.nationality,
            'cultureoflife': self.cultureoflife,
            'familyname1': self.familyname1,
            'familyname2': self.familyname2,
            'familyname3': self.familyname3,
            'familyname4': self.familyname4,
            'familyname5': self.familyname5,
            'religion': self.religion,
            'caste': self.caste,
        }