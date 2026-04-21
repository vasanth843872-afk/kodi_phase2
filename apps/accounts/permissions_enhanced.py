"""
Enhanced permissions for staff role management
"""
from rest_framework import permissions
from django.contrib.auth import get_user_model

User = get_user_model()

class IsStaffUser(permissions.BasePermission):
    """
    Permission to only allow staff users.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

class IsSuperUser(permissions.BasePermission):
    """
    Permission to only allow superusers.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser

class IsModeratorOrAbove(permissions.BasePermission):
    """
    Permission to only allow moderators and above.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'is_moderator') and request.user.is_moderator

class IsAdminOrAbove(permissions.BasePermission):
    """
    Permission to only allow administrators and above.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'is_administrator') and request.user.is_administrator

class IsSuperAdmin(permissions.BasePermission):
    """
    Permission to only allow super administrators.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_superuser and 
            hasattr(request.user, 'staff_role') and 
            request.user.staff_role == 'super_admin'
        )

class CanManageUsers(permissions.BasePermission):
    """
    Permission to allow staff users to manage other users.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'can_manage_users') and request.user.can_manage_users

class CanManagePosts(permissions.BasePermission):
    """
    Permission to allow staff users to manage all posts.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'can_manage_posts') and request.user.can_manage_posts

class CanManageEvents(permissions.BasePermission):
    """
    Permission to allow staff users to manage events.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'can_manage_events') and request.user.can_manage_events

class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to allow staff users to view analytics.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'can_view_analytics') and request.user.can_view_analytics

class CanModerateContent(permissions.BasePermission):
    """
    Permission to allow staff users to moderate content.
    """
    
    def has_permission(self, request, view):
        return request.user and hasattr(request.user, 'can_moderate_content') and request.user.can_moderate_content

class HasProfileAccess(permissions.BasePermission):
    """
    Permission to allow users with complete profiles.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has complete profile
        return hasattr(request.user, 'profile') and request.user.profile is not None

class IsOwnerOrStaff(permissions.BasePermission):
    """
    Permission to allow resource owner or any staff user.
    """
    
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True
        
        # Check if user owns the object
        if hasattr(obj, 'author'):
            return obj.author == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'linked_user'):
            return obj.linked_user == request.user
        
        return False
