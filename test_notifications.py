#!/usr/bin/env python
"""
Test script to check notification system
"""
import os
import sys
import django

# Setup Django
sys.path.append('e:/kODI/KODI10/KODi3')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'KODi3.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.event_management.models import Event
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService, get_user_display_name

User = get_user_model()

def test_notification_system():
    print("=== Testing Notification System ===")
    
    # Check users
    users = User.objects.all()[:5]
    print(f"Total users: {User.objects.count()}")
    for user in users:
        print(f"  - {user.id}: {user} (Staff: {user.is_staff})")
    
    # Check events
    events = Event.objects.all()[:5]
    print(f"\nTotal events: {Event.objects.count()}")
    for event in events:
        print(f"  - {event.id}: {event.title} (Status: {event.status}, Creator: {event.created_by})")
    
    # Check notifications
    notifications = Notification.objects.all()[:10]
    print(f"\nTotal notifications: {Notification.objects.count()}")
    for notif in notifications:
        print(f"  - {notif.id}: {notif.title} -> {notif.user} ({notif.created_at})")
    
    # Test creating a notification
    if events and users:
        print("\n=== Testing Notification Creation ===")
        event = events[0]
        user = users[0]
        
        print(f"Testing with event: {event.title}")
        print(f"Testing with user: {user}")
        
        try:
            notifications = NotificationService.create_event_notification(
                event=event,
                notification_type='event_updated',
                users=[user],
                message=f"Test notification for {event.title}",
                actor=None
            )
            print(f"Created {len(notifications)} test notifications")
            
            if notifications:
                notif = notifications[0]
                print(f"Notification details:")
                print(f"  - ID: {notif.id}")
                print(f"  - Title: {notif.title}")
                print(f"  - Message: {notif.message}")
                print(f"  - User: {notif.user}")
                print(f"  - Type: {notif.notification_type}")
                print(f"  - Extra Data: {notif.extra_data}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_notification_system()
