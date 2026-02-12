from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL

class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)  # Email is unique in AdminProfile
    phone = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='admin_profiles/', blank=True, null=True)
    admin_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    last_password_change = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Admin Profile"
        verbose_name_plural = "Admin Profiles"
    
    def __str__(self):
        return f"{self.full_name} ({self.user.mobile_number})"
    
    def save(self, *args, **kwargs):
        if not self.admin_id:
            self.admin_id = f"ADM-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

class StaffPermission(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_permissions')
    user_type = models.CharField(max_length=10, choices=[('admin', 'Admin'), ('staff', 'Staff')], default='staff')
    can_view_dashboard = models.BooleanField(default=True)
    can_manage_dashboard = models.BooleanField(default=True)
    can_create_content = models.BooleanField(default=True)
    can_edit_content = models.BooleanField(default=True)
    can_delete_content = models.BooleanField(default=True)
    can_view_content = models.BooleanField(default=True)
    can_view_users = models.BooleanField(default=True)
    can_edit_users = models.BooleanField(default=False)
    can_delete_users = models.BooleanField(default=False)
    can_manage_admin = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=True)
    can_export_data = models.BooleanField(default=True)
    can_send_notifications = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Staff Permission"
        verbose_name_plural = "Staff Permissions"
    
    def __str__(self):
        return f"{self.user.mobile_number} - {self.user_type}"

class AdminActivityLog(models.Model):
    ACTION_CHOICES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('password_change', 'Password Change'),
        ('status_change', 'Status Change'),
    )
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='admin_activity_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.mobile_number if self.user else 'System'} - {self.action}"

@receiver(post_save, sender=User)
def create_admin_profile_for_staff(sender, instance, created, **kwargs):
    if instance.is_staff and not hasattr(instance, 'admin_profile'):
        # Create admin profile without email for now
        AdminProfile.objects.create(
            user=instance,
            full_name=f"Admin {instance.mobile_number}",
            email=f"{instance.mobile_number}@admin.local"  # Default email
        )
    
    if instance.is_staff and not hasattr(instance, 'staff_permissions'):
        user_type = 'admin' if instance.is_superuser else 'staff'
        StaffPermission.objects.create(user=instance, user_type=user_type, is_active=True)
        


# admin_app/models.py (add to your existing file)
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL

# ... existing AdminProfile, StaffPermission, AdminActivityLog models ...

class RelationManagementPermission(models.Model):
    """Permissions specifically for relation management."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='relation_permissions')
    
    # Relation management permissions
    can_manage_fixed_relations = models.BooleanField(default=False)
    can_manage_language_religion = models.BooleanField(default=False)
    can_manage_caste_overrides = models.BooleanField(default=False)
    can_manage_family_overrides = models.BooleanField(default=False)
    can_view_relation_analytics = models.BooleanField(default=True)
    can_export_relation_data = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Relation Management Permission"
        verbose_name_plural = "Relation Management Permissions"
    
    def __str__(self):
        return f"Relation Permissions - {self.user.mobile_number}"

class RelationAdminActivityLog(models.Model):
    """Activity log specifically for relation management."""
    ACTION_CHOICES = (
        ('relation_create', 'Relation Created'),
        ('relation_update', 'Relation Updated'),
        ('relation_delete', 'Relation Deleted'),
        ('override_create', 'Override Created'),
        ('override_update', 'Override Updated'),
        ('override_delete', 'Override Deleted'),
        ('bulk_import', 'Bulk Import'),
        ('export', 'Export'),
    )
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    relation_code = models.CharField(max_length=50, blank=True, null=True)
    affected_level = models.CharField(max_length=20, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Relation Activity Log"
        verbose_name_plural = "Relation Activity Logs"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.mobile_number if self.user else 'System'} - {self.action}"

@receiver(post_save, sender=User)
def create_default_relation_permissions(sender, instance, created, **kwargs):
    """Create default relation permissions for staff users."""
    if created and instance.is_staff:
        try:
            # Check if staff permission exists
            staff_perm = StaffPermission.objects.get(user=instance)
            
            # Create relation permissions based on user type
            if staff_perm.user_type == 'admin':
                # Admins get full permissions
                RelationManagementPermission.objects.create(
                    user=instance,
                    can_manage_fixed_relations=True,
                    can_manage_language_religion=True,
                    can_manage_caste_overrides=True,
                    can_manage_family_overrides=True,
                    can_export_relation_data=True
                )
            elif staff_perm.user_type == 'staff':
                # Staff get limited permissions
                RelationManagementPermission.objects.create(
                    user=instance,
                    can_manage_language_religion=staff_perm.can_create_content,
                    can_manage_caste_overrides=staff_perm.can_edit_content,
                    can_manage_family_overrides=False  # Typically only admins manage family overrides
                )
        except StaffPermission.DoesNotExist:
            pass