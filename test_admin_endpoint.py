#!/usr/bin/env python
"""
Test script to check admin endpoint
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
from django.urls import reverse
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request

User = get_user_model()

def test_admin_endpoint():
    print("=== Testing Admin Endpoint ===")
    
    # Get admin user
    admin_user = User.objects.filter(is_staff=True).first()
    if not admin_user:
        print("No admin user found!")
        return
    
    print(f"Using admin user: {admin_user}")
    
    # Get a test event
    event = Event.objects.first()
    if not event:
        print("No events found!")
        return
    
    print(f"Using event: {event.title} (ID: {event.id})")
    print(f"Current status: {event.status}")
    
    # Create request factory
    factory = APIRequestFactory()
    
    # Test approve action
    print("\n=== Testing Approve Action ===")
    request = factory.post(f'/events/{event.id}/moderate/', {
        'action': 'approve',
        'note': 'Test approval'
    })
    
    # Add user to request
    request.user = admin_user
    
    # Create DRF request
    drf_request = Request(request)
    drf_request.user = admin_user
    
    print(f"Request data: {drf_request.data}")
    print(f"Request user: {drf_request.user}")
    
    # Try to call the moderate action
    try:
        from apps.event_management.views import EventViewSet
        viewset = EventViewSet()
        viewset.request = drf_request
        viewset.format_kwarg = None
        viewset.kwargs = {'pk': event.id}
        
        # Call the moderate action
        response = viewset.moderate(drf_request, pk=event.id)
        print(f"Response: {response.data}")
        print(f"Status code: {response.status_code}")
        
        # Check if event was updated
        event.refresh_from_db()
        print(f"New event status: {event.status}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_admin_endpoint()
