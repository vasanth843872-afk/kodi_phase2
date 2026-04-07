#!/usr/bin/env python
"""
Debug the service method directly
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.posts.models import Post, PostAudience
from apps.posts.services import PostVisibilityService

User = get_user_model()

def debug_service():
    print("Debugging service method...")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"User: {user.id}")
    
    # Check what the service method returns
    print("\n=== Testing _get_posts_from_precomputed_audience ===")
    
    # Get posts using service method
    posts = PostVisibilityService._get_posts_from_precomputed_audience(user, 20, 0)
    print(f"Service returned {posts.count()} posts")
    
    for post in posts:
        print(f"  - Post {post.id}: {post.content[:30]}...")
    
    # Test the full service method
    print("\n=== Testing get_visible_posts_for_user ===")
    visible_posts = PostVisibilityService.get_visible_posts_for_user(user, 20, 0)
    print(f"get_visible_posts_for_user returned {visible_posts.count()} posts")
    
    # Test the feed method
    print("\n=== Testing get_feed_with_engagement_data ===")
    feed_data = PostVisibilityService.get_feed_with_engagement_data(user, 20, 0)
    print(f"get_feed_with_engagement_data returned {len(feed_data)} posts")
    
    if feed_data:
        print("First post in feed:")
        first_post = feed_data[0]
        print(f"  ID: {first_post.get('id')}")
        print(f"  Content: {first_post.get('content', '')[:30]}...")
        print(f"  Media count: {first_post.get('media_count', 0)}")
        print(f"  Media array: {len(first_post.get('media', []))}")

if __name__ == '__main__':
    debug_service()
