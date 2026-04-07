#!/usr/bin/env python
"""
Detailed test to find the exact source of the '_meta' error
"""
import os
import sys
import django
import traceback

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.posts.models import PostVisibilityRule, Post
from apps.posts.services import PostVisibilityService

User = get_user_model()

def test_direct_service():
    print("Testing direct service call...")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"Using user: {user.id} - {user.mobile_number}")
    
    # Create a simple post
    post = Post.objects.create(
        author=user,
        content='Test post for service',
        visibility='connections'
    )
    
    print(f"Created post: {post.id}")
    
    try:
        # Test the service method directly
        print("Calling precompute_audience_for_post...")
        PostVisibilityService.precompute_audience_for_post(post)
        print("✅ Service call successful!")
        
    except Exception as e:
        print(f"❌ Error in service: {e}")
        print("Full traceback:")
        traceback.print_exc()
    
    finally:
        post.delete()

def test_api_step_by_step():
    print("\n" + "="*50)
    print("Testing API step by step...")
    
    client = APIClient()
    user = User.objects.first()
    
    if not user:
        print("No users found!")
        return
    
    client.force_authenticate(user=user)
    
    # Test data
    test_data = {
        'content': 'jjhw',
        'visibility': 'connections'
    }
    
    print(f"Testing with data: {test_data}")
    
    try:
        # Create the post manually first to see if that works
        print("Step 1: Creating post manually...")
        post = Post.objects.create(
            author=user,
            content=test_data['content'],
            visibility=test_data['visibility']
        )
        print(f"✅ Manual post creation successful: {post.id}")
        
        # Test the service call
        print("Step 2: Testing service call...")
        PostVisibilityService.precompute_audience_for_post(post)
        print("✅ Service call successful!")
        
        # Clean up
        post.delete()
        
        # Now test the full API
        print("Step 3: Testing full API...")
        response = client.post('/api/posts/create/', data=test_data, format='json')
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.data}")
        
        if response.status_code == 201:
            print("✅ API call successful!")
        else:
            print("❌ API call failed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Full traceback:")
        traceback.print_exc()

if __name__ == '__main__':
    test_direct_service()
    test_api_step_by_step()
