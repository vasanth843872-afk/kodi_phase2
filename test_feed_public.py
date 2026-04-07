#!/usr/bin/env python
"""
Test the feed endpoint with public posts
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
from apps.posts.services import PostVisibilityService

User = get_user_model()

def test_feed_public():
    print("Testing feed endpoint with public posts...")
    
    client = APIClient()
    user = User.objects.first()
    
    if not user:
        print("No users found!")
        return
    
    client.force_authenticate(user=user)
    
    # Create a test post
    post = Post.objects.create(
        author=user,
        content='Test public post for feed',
        visibility='public'
    )
    
    print(f"Created test post: {post.id}")
    
    # Manually add to audience for testing
    PostAudience.objects.create(
        post=post,
        user=user,
        visibility_reason='public'
    )
    
    print(f"Added post to audience for user: {user.id}")
    
    try:
        response = client.get('/api/posts/feed/?page=1&page_size=20')
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            print(f"✅ Feed successful!")
            print(f"Total posts: {data.get('count', 0)}")
            print(f"Posts returned: {len(data.get('results', []))}")
            
            # Show first post details
            if data.get('results'):
                first_post = data['results'][0]
                print(f"First post ID: {first_post.get('id')}")
                print(f"First post content: {first_post.get('content', '')[:50]}...")
                print(f"First post visibility: {first_post.get('visibility')}")
            else:
                print("No posts in feed - checking audience table...")
                audience_count = PostAudience.objects.filter(user=user).count()
                print(f"Audience entries for user: {audience_count}")
                
                # Check if our post is in the audience
                in_audience = PostAudience.objects.filter(post=post, user=user).exists()
                print(f"Test post in audience: {in_audience}")
                
        else:
            print(f"❌ Feed failed: {response.data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        PostAudience.objects.filter(post=post).delete()
        post.delete()
        print("Cleaned up test data")

if __name__ == '__main__':
    test_feed_public()
