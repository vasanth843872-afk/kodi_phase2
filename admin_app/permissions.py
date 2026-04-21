from rest_framework import permissions
from .models import StaffPermission

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            return staff_perm.user_type == 'admin' and staff_perm.is_active
        except StaffPermission.DoesNotExist:
            return False

class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            return staff_perm.user_type == 'staff' and staff_perm.is_active
        except StaffPermission.DoesNotExist:
            return False

class CanViewUsers(permissions.BasePermission):
    def has_permission(self, request, view):
        try:
            if not request.user.is_authenticated:
                return False
            staff_perm = StaffPermission.objects.get(user=request.user)
            if staff_perm.user_type == 'admin':
                return True
            allowed = staff_perm.can_view_users and staff_perm.is_active
            # logger.debug(f"User {request.user.mobile_number} can_view_users={staff_perm.can_view_users}, allowed={allowed}")
            return allowed
        except StaffPermission.DoesNotExist:
            return False
        except Exception as e:
            # logger.error(f"Permission check error: {e}", exc_info=True)
            return False   # Important: fail closed
        
from rest_framework import permissions

class HasRelationPermission(permissions.BasePermission):
    """Custom permission for relation management."""
    
    def __init__(self, permission_name):
        self.permission_name = permission_name
    
    def has_permission(self, request, view):
        # Admins have all permissions
        if request.user.is_superuser or request.user.groups.filter(name='Admin').exists():
            return True
        
        # Check specific relation permission
        from .models import RelationManagementPermission
        try:
            relation_perm = RelationManagementPermission.objects.get(user=request.user)
            return getattr(relation_perm, self.permission_name, False)
        except RelationManagementPermission.DoesNotExist:
            return False

# Convenience permissions
class CanManageFixedRelations(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_fixed_relations')

class CanManageLanguagelifestyle(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_language_lifestyle')

class CanManagefamilyname8Overrides(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_familyname8_overrides')

class CanManageFamilyOverrides(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_family_overrides')

class CanViewRelationAnalytics(HasRelationPermission):
    def __init__(self):
        super().__init__('can_view_relation_analytics')

class CanExportRelationData(HasRelationPermission):
    def __init__(self):
        super().__init__('can_export_relation_data')
        
class CanManageProfileOverrides(HasRelationPermission):
    """Permission for managing profile overrides."""
    def __init__(self):
        super().__init__('can_manage_profile_overrides')
        
class CanManageChat(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            # Admin can always manage posts
            if staff_perm.user_type == 'admin':
                return True
            return staff_perm.can_manage_chat and staff_perm.is_active
        except StaffPermission.DoesNotExist:
            return False
        
class CanManagePost(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            if staff_perm.user_type == 'admin':
                return True
            return staff_perm.can_manage_post and staff_perm.is_active
        except StaffPermission.DoesNotExist:
            return False
        
class CanManageEvent(permissions.BasePermission):
    """
    Allows access if the user is an admin OR has the 'can_manage_event' staff permission.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin always has permission
        if request.user.is_staff or request.user.is_superuser:
            return True

        # Check staff permission
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            return staff_perm.is_active and staff_perm.can_manage_event
        except StaffPermission.DoesNotExist:
            return False