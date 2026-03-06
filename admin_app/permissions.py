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
        if not request.user.is_authenticated:
            return False
        
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            if staff_perm.user_type == 'admin':
                return True
            return staff_perm.can_view_users and staff_perm.is_active
        except StaffPermission.DoesNotExist:
            return False
        
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

class CanManageLanguageReligion(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_language_religion')

class CanManageCasteOverrides(HasRelationPermission):
    def __init__(self):
        super().__init__('can_manage_caste_overrides')

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