#!/usr/bin/env python
"""
Debug the feed endpoint
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

def debug_feed():
    print("Debugging feed endpoint...")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"User: {user.id} - {user.mobile_number}")
    
    # Create a test post
    post = Post.objects.create(
        author=user,
        content='Debug test post',
        visibility='public'
    )
    
    # Add to audience
    PostAudience.objects.create(
        post=post,
        user=user,
        visibility_reason='public'
    )
    
    print(f"Created post: {post.id}")
    
    # Debug the precomputed audience method
    print("\n=== Debugging _get_posts_from_precomputed_audience ===")
    
    # Get post_ids directly
    post_ids = PostAudience.objects.filter(
        user=user
    ).select_related('post').order_by('-post__created_at').values_list('post', flat=True)
    
    print(f"All post_ids for user: {list(post_ids)}")
    
    # Get with limit/offset
    post_ids_limited = PostAudience.objects.filter(
        user=user
    ).select_related('post').order_by('-post__created_at').values_list('post', flat=True)[0:20]
    
    print(f"Limited post_ids: {list(post_ids_limited)}")
    
    # Get the posts
    posts = Post.objects.filter(
        id__in=post_ids_limited,
        is_active=True,
        is_deleted=False
    )
    
    print(f"Posts found: {posts.count()}")
    for p in posts:
        print(f"  - Post {p.id}: {p.content[:30]}...")
    
    # Test the service method directly
    print("\n=== Testing service method ===")
    service_posts = PostVisibilityService._get_posts_from_precomputed_audience(user, 20, 0)
    print(f"Service posts count: {service_posts.count()}")
    
    # Clean up
    PostAudience.objects.filter(post=post).delete()
    post.delete()
    print("\nCleaned up")

if __name__ == '__main__':
    debug_feed()
