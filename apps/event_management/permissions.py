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
        return request.user.is_staff or request.user.groups.filter(name='Moderators').exists()


class CanCreateEventType(permissions.BasePermission):
    """
    Anyone can create event types
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated