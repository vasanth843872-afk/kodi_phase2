#!/usr/bin/env python
"""
Debug media directly
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

User = get_user_model()

def debug_media():
    print("Debugging media directly...")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    # Get a post from the service
    from apps.posts.services import PostVisibilityService
    posts = PostVisibilityService._get_posts_from_precomputed_audience(user, 20, 0)
    
    if posts:
        post = posts.first()
        print(f"Debugging post {post.id}")
        
        # Check media in database
        media_count = PostMedia.objects.filter(post=post).count()
        print(f"Media count in DB: {media_count}")
        
        media_items = PostMedia.objects.filter(post=post)
        print(f"Media items:")
        for media in media_items:
            print(f"  - Media {media.id}: {media.media_type} - {media.caption}")
        
        # Check post.media relationship
        print(f"post.media.all(): {post.media.all()}")
        print(f"post.media.count(): {post.media.count()}")
        print(f"hasattr(post, 'media'): {hasattr(post, 'media')}")
        
        # Check if media is prefetched
        print(f"post._prefetched_objects_cache: {getattr(post, '_prefetched_objects_cache', None)}")

if __name__ == '__main__':
    debug_media()
