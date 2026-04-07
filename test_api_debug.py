#!/usr/bin/env python
"""
Test the API with debugging to find the exact error
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.posts.models import PostVisibilityRule

User = get_user_model()

def test_api_view():
    print("Testing API view...")
    
    # Create DRF client
    client = APIClient()
    
    # Get a user
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"Using user: {user.id} - {user.mobile_number}")
    
    # Authenticate the client
    client.force_authenticate(user=user)
    
    # Create a visibility rule
    rule, created = PostVisibilityRule.objects.get_or_create(
        name='API Test Rule',
        defaults={
            'description': 'Test rule for API debugging',
            'caste_criteria': ['OC'],
            'religion_criteria': ['Hindu'],
            'is_active': True,
            'created_by': user
        }
    )
    
    print(f"Rule: {rule.id} - {rule.name}")
    
    # Test data similar to your payload
    test_data = {
        'content': 'jjhw',
        'visibility': 'connections'  # Test with simple visibility first
    }
    
    print(f"Testing with data: {test_data}")
    
    try:
        response = client.post('/api/posts/create/', data=test_data, format='json')
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.data}")
        
        if response.status_code == 201:
            print("✅ Success with connections visibility!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test with custom visibility
    print("\n" + "="*50)
    print("Testing with custom visibility...")
    
    custom_data = {
        'content': 'jjhw',
        'visibility': 'custom',
        'custom_visibility_rule': rule.id  # Pass as integer
    }
    
    print(f"Testing with custom data: {custom_data}")
    
    try:
        response = client.post('/api/posts/create/', data=custom_data, format='json')
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.data}")
        
        if response.status_code == 201:
            print("✅ Success with custom visibility!")
        else:
            print("❌ Failed with custom visibility")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_api_view()
