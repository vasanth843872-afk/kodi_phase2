from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from datetime import timedelta


class UserManager(BaseUserManager):
    """Custom user manager for mobile-based authentication."""
    
    def create_user(self, mobile_number, password=None, is_staff=False, **extra_fields):  # ✅ Add parameters
        if not mobile_number:
            raise ValueError('Mobile number is required')
        
        user = self.model(mobile_number=mobile_number, **extra_fields)
        
        # Only set password for staff/admin users
        if password and is_staff:
            user.set_password(password)
            
        user.save(using=self._db)
        return user
    
    def create_superuser(self, mobile_number, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(mobile_number,password, **extra_fields)
    
    def create_staff_user(self, mobile_number, password=None, **extra_fields):
        """Convenience method to create staff users with passwords."""
        extra_fields.setdefault('is_staff', True)
        return self.create_user(mobile_number, password, is_staff=True, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model using mobile number as primary identifier."""
    
    id = models.BigAutoField(primary_key=True)
    mobile_number = models.CharField(max_length=15, unique=True, db_index=True)
    is_mobile_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    is_auto_login_enabled = models.BooleanField(default=False)
    auto_login_last_used = models.DateTimeField(null=True, blank=True)
    auto_login_token = models.CharField(max_length=100, blank=True, null=True)
    
    # OTP fields
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['mobile_number', 'is_active']),
        ]
    
    def __str__(self):
        return self.mobile_number
    
    def generate_otp(self):
        """Generate and store OTP."""
        import random
        # self.otp = str(random.randint(100000, 999999))
        self.otp="123456"
        self.otp_created_at = timezone.now()
        self.save()
        return self.otp
    
    def verify_otp(self, otp):
        if not self.otp or self.otp != otp:
            return False

        if not self.otp_created_at:
            return False

        if timezone.now() > self.otp_created_at + timedelta(minutes=5):
            return False

        # OTP is valid
        self.is_mobile_verified = True
        self.otp = None
        self.otp_created_at = None
        self.save(update_fields=[
            "is_mobile_verified",
            "otp",
            "otp_created_at"
        ])

        return True

class OTPLog(models.Model):
    """Track OTP requests for security."""
    mobile_number = models.CharField(max_length=15, db_index=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'otp_logs'
        indexes = [
            models.Index(fields=['mobile_number', 'created_at']),
        ]