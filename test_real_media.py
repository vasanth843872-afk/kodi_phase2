#!/usr/bin/env python
"""
Test with real posts that have media
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
from apps.posts.models import Post, PostMedia

User = get_user_model()

def test_real_media():
    print("Testing with real posts that have media...")
    
    # Find posts that actually have media
    posts_with_media = Post.objects.filter(
        is_active=True,
        is_deleted=False
    ).filter(media__isnull=False).distinct()
    
    print(f"Posts with media in DB: {posts_with_media.count()}")
    
    if posts_with_media.exists():
        post = posts_with_media.first()
        print(f"Testing post {post.id}")
        
        # Check its media
        media_items = PostMedia.objects.filter(post=post)
        print(f"Media items for post {post.id}: {media_items.count()}")
        
        for media in media_items:
            print(f"  - Media {media.id}: {media.media_type} - {media.caption}")
            print(f"    File: {media.file.url if media.file else 'No file'}")
        
        # Test the feed with the user who created this post
        user = post.author
        client = APIClient()
        client.force_authenticate(user=user)
        
        try:
            response = client.get('/api/posts/feed/?page=1&page_size=20')
            print(f"Feed response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.data
                feed_posts = data.get('results', [])
                
                # Find this post in the feed
                for feed_post in feed_posts:
                    if feed_post.get('id') == post.id:
                        print(f"Found post {post.id} in feed!")
                        print(f"Media count in feed: {feed_post.get('media_count', 0)}")
                        print(f"Media array length: {len(feed_post.get('media', []))}")
                        
                        if feed_post.get('media'):
                            first_media = feed_post['media'][0]
                            print(f"First media in feed: {first_media.get('id')} - {first_media.get('media_type')}")
                        else:
                            print("❌ No media array in feed response!")
                        break
                else:
                    print(f"❌ Post {post.id} not found in feed!")
            else:
                print(f"❌ Feed failed: {response.data}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No posts with media found in database!")

if __name__ == '__main__':
    test_real_media()
