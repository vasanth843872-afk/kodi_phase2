"""
Custom permissions for staff role management
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

class IsStaffOrReadOnly(permissions.BasePermission):
    """
    Permission to allow staff users to write, others to read.
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff

class CanManageUsers(permissions.BasePermission):
    """
    Permission to allow staff users to manage other users.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class CanManagePosts(permissions.BasePermission):
    """
    Permission to allow staff users to manage all posts.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class CanManageEvents(permissions.BasePermission):
    """
    Permission to allow staff users to manage events.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class CanManageRelations(permissions.BasePermission):
    """
    Permission to allow staff users to manage relations.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class CanViewAnalytics(permissions.BasePermission):
    """
    Permission to allow staff users to view analytics.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class CanModerateContent(permissions.BasePermission):
    """
    Permission to allow staff users to moderate content.
    """
    
    def has_permission(self, request, view):
        return request.user and (
            request.user.is_staff or 
            request.user.is_superuser
        )

class HasProfileAccess(permissions.BasePermission):
    """
    Permission to allow users with complete profiles.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has complete profile
        return hasattr(request.user, 'profile') and request.user.profile is not None
