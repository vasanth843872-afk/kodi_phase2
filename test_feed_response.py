#!/usr/bin/env python
"""
Check the actual feed response
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

User = get_user_model()

def test_feed_response():
    print("Testing feed response...")
    
    client = APIClient()
    user = User.objects.first()
    
    if not user:
        print("No users found!")
        return
    
    client.force_authenticate(user=user)
    
    try:
        response = client.get('/api/posts/feed/?page=1&page_size=20')
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            print(f"Response keys: {list(data.keys())}")
            
            posts = data.get('posts', [])
            pagination = data.get('pagination', {})
            
            print(f"Posts in response: {len(posts)}")
            print(f"Pagination: {pagination}")
            
            # Show all post IDs in response
            post_ids_in_response = [p.get('id') for p in posts]
            print(f"Post IDs in response: {post_ids_in_response}")
            
            # Check if we have posts with media
            posts_with_media = [p for p in posts if p.get('media_count', 0) > 0]
            print(f"Posts with media in response: {len(posts_with_media)}")
            
            if posts_with_media:
                first_media_post = posts_with_media[0]
                print(f"First post with media:")
                print(f"  ID: {first_media_post.get('id')}")
                print(f"  Media count: {first_media_post.get('media_count')}")
                print(f"  Media array length: {len(first_media_post.get('media', []))}")
                
                if first_media_post.get('media'):
                    first_media = first_media_post['media'][0]
                    print(f"  First media: {first_media.get('id')} - {first_media.get('media_type')}")
                else:
                    print("  ❌ No media array found!")
        else:
            print(f"❌ Feed failed: {response.data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_feed_response()
