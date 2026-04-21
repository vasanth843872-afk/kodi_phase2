"""
Helper functions for post notifications
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.relations.models import UserConnection
from apps.genealogy.models import Person

User = get_user_model()


def get_users_for_post_notification(post, request_user):
    """Get users who should receive post notifications"""
    users = set()
    
    # Get users who can see this post based on visibility
    if post.visibility == 'public':
        # For public posts, notify connected users
        try:
            user_person = request_user.person_record
        except Person.DoesNotExist:
            return []
        
        # Get all accepted connections where request_user is either user1 or user2
        connections = UserConnection.objects.filter(
            Q(user1=request_user) | Q(user2=request_user),
            is_active=True,
            is_blocked=False
        )
        
        # Extract the other user's ID from each connection
        connected_user_ids = []
        for conn in connections:
            if conn.user1 == request_user:
                connected_user_ids.append(conn.user2_id)
            else:
                connected_user_ids.append(conn.user1_id)
        
        users.update(connected_user_ids)
        
    elif post.visibility == 'connections':
        # For connection posts, notify all connections (same logic as above)
        connections = UserConnection.objects.filter(
            Q(user1=request_user) | Q(user2=request_user),
            is_active=True,
            is_blocked=False
        )
        
        connected_user_ids = []
        for conn in connections:
            if conn.user1 == request_user:
                connected_user_ids.append(conn.user2_id)
            else:
                connected_user_ids.append(conn.user1_id)
        
        users.update(connected_user_ids)
    
    # Remove current user
    users.discard(request_user.id)  # compare by ID, not object
    
    # Convert to User objects
    return User.objects.filter(id__in=users)