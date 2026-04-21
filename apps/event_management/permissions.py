from rest_framework import permissions

class CanCreateEvent(permissions.BasePermission):
    """
    Check if user can create events
    """
    def has_permission(self, request, view):
        user = request.user
        
        # Admin can always create
        if user.is_staff:
            return True
        
        # Check user restrictions
        try:
            restriction = user.event_restrictions
            if not restriction.can_create_events:
                return False
        except:
            pass
        
        return True


class CanViewEvent(permissions.BasePermission):
    """
    Check if user can view a specific event
    """
    def has_object_permission(self, request, view, obj):
        return obj.is_visible_to(request.user)


class IsEventCreatorOrAdmin(permissions.BasePermission):
    """
    Only event creator or admin can edit/delete
    """
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.created_by == request.user


class IsAdminOrModerator(permissions.BasePermission):
    """
    Only admin or moderator can moderate
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # 1. Admin / superuser always allowed
        if request.user.is_staff or request.user.is_superuser:
            return True

        # 2. Check staff permission
        try:
            staff_perm = StaffPermission.objects.get(user=request.user)
            return staff_perm.is_active and staff_perm.can_manage_event
        except StaffPermission.DoesNotExist:
            return False

class CanCreateEventType(permissions.BasePermission):
    """
    Anyone can create event types
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated