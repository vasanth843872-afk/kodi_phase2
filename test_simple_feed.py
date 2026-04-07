#!/usr/bin/env python
"""
Simple test to check feed with existing posts
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
from apps.posts.models import Post, PostAudience

User = get_user_model()

def test_simple_feed():
    print("Testing feed with existing posts...")
    
    client = APIClient()
    user = User.objects.first()
    
    if not user:
        print("No users found!")
        return
    
    client.force_authenticate(user=user)
    
    # Check existing posts
    existing_posts = Post.objects.filter(author=user, is_active=True, is_deleted=False)
    print(f"Total existing posts: {existing_posts.count()}")
    
    # Check existing audience
    existing_audience = PostAudience.objects.filter(user=user)
    print(f"Total audience entries: {existing_audience.count()}")
    
    # Show post IDs in audience
    audience_post_ids = list(existing_audience.values_list('post_id', flat=True))
    print(f"Post IDs in audience: {audience_post_ids}")
    
    # Try feed
    try:
        response = client.get('/api/posts/feed/?page=1&page_size=20')
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            print(f"✅ Feed successful!")
            print(f"Total posts in feed: {data.get('count', 0)}")
            print(f"Posts returned: {len(data.get('results', []))}")
        else:
            print(f"❌ Feed failed: {response.data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_simple_feed()
