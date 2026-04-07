#!/usr/bin/env python
"""
Fix audience entries for existing posts
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

def fix_audience():
    print("Fixing audience entries for existing posts...")
    
    # Get all posts without audience
    posts_without_audience = Post.objects.filter(
        is_active=True,
        is_deleted=False
    ).exclude(
        id__in=PostAudience.objects.all().values_list('post_id', flat=True)
    )
    
    print(f"Posts without audience: {posts_without_audience.count()}")
    
    fixed_count = 0
    for post in posts_without_audience:
        print(f"Processing post {post.id}: {post.content[:30]}...")
        
        try:
            # Precompute audience for this post
            PostVisibilityService.precompute_audience_for_post(post)
            fixed_count += 1
            print(f"✅ Fixed audience for post {post.id}")
            
        except Exception as e:
            print(f"❌ Error fixing post {post.id}: {e}")
    
    print(f"\nFixed audience for {fixed_count} posts!")
    
    # Verify the fix
    user = User.objects.first()
    if user:
        audience_count = PostAudience.objects.filter(user=user).count()
        print(f"Total audience entries for user {user.id}: {audience_count}")

if __name__ == '__main__':
    fix_audience()
