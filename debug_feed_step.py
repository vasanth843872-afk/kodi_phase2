#!/usr/bin/env python
"""
Debug feed step by step
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
from apps.posts.models import Post, PostAudience, PostMedia
from apps.posts.services import PostVisibilityService

User = get_user_model()

def debug_feed_step():
    print("Debugging feed step by step...")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"User: {user.id}")
    
    # Check the post we're looking for
    target_post = Post.objects.filter(media__isnull=False).first()
    if not target_post:
        print("No posts with media found!")
        return
        
    print(f"Target post: {target_post.id}")
    
    # Check if user has audience entry for this post
    audience_entry = PostAudience.objects.filter(post=target_post, user=user).first()
    print(f"User has audience for target post: {audience_entry is not None}")
    
    if audience_entry:
        print(f"Audience entry: {audience_entry.visibility_reason}")
    
    # Test the exact service method call
    print("\n=== Testing _get_posts_from_precomputed_audience ===")
    posts = PostVisibilityService._get_posts_from_precomputed_audience(user, 20, 0)
    print(f"Service returned {posts.count()} posts")
    
    for post in posts:
        print(f"  - Post {post.id}: {post.content[:30]}...")
        if post.id == target_post.id:
            print(f"    ✅ Found target post in results!")
        else:
            print(f"    ❌ Different post")
    
    # Check if target post is in the returned posts
    post_ids = [p.id for p in posts]
    if target_post.id in post_ids:
        print(f"✅ Target post ID {target_post.id} is in service results!")
    else:
        print(f"❌ Target post ID {target_post.id} NOT in service results!")
        print(f"Post IDs returned: {post_ids}")

if __name__ == '__main__':
    debug_feed_step()
