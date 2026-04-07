#!/usr/bin/env python
"""
Test feed endpoint with media posts
"""
import os
import sys
import django
from io import BytesIO

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.posts.models import Post, PostAudience, PostMedia
from apps.posts.services import PostVisibilityService

User = get_user_model()

def test_feed_with_media():
    print("Testing feed endpoint with media...")
    
    client = APIClient()
    user = User.objects.first()
    
    if not user:
        print("No users found!")
        return
    
    client.force_authenticate(user=user)
    
    # Create a test post
    post = Post.objects.create(
        author=user,
        content='Test post with media',
        visibility='public'
    )
    
    # Add to audience
    PostAudience.objects.create(
        post=post,
        user=user,
        visibility_reason='public'
    )
    
    # Create media (simulate file upload)
    from django.core.files.base import ContentFile
    
    # Create a simple test image file
    test_image = ContentFile(b"fake_image_data", "test_image.jpg")
    
    media = PostMedia.objects.create(
        post=post,
        file=test_image,
        media_type='image',
        original_filename='test_image.jpg',
        file_size=len(b"fake_image_data"),
        mime_type='image/jpeg',
        caption='Test image caption'
    )
    
    print(f"Created post: {post.id}")
    print(f"Created media: {media.id}")
    print(f"Media file URL: {media.file.url if media.file else 'No file'}")
    
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
                print(f"Media count: {first_post.get('media_count', 0)}")
                
                # Check media array
                media_array = first_post.get('media', [])
                print(f"Media array length: {len(media_array)}")
                
                if media_array:
                    first_media = media_array[0]
                    print(f"First media ID: {first_media.get('id')}")
                    print(f"First media type: {first_media.get('media_type')}")
                    print(f"First media caption: {first_media.get('caption')}")
                    print(f"First media file: {first_media.get('file')}")
                else:
                    print("❌ No media array found in response!")
        else:
            print(f"❌ Feed failed: {response.data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        PostMedia.objects.filter(post=post).delete()
        PostAudience.objects.filter(post=post).delete()
        post.delete()
        print("Cleaned up test data")

if __name__ == '__main__':
    test_feed_with_media()
