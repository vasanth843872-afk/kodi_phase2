#!/usr/bin/env python
"""
Test the feed endpoint
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

def test_feed():
    print("Testing feed endpoint...")
    
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
            print(f"✅ Feed successful!")
            print(f"Total posts: {data.get('count', 0)}")
            print(f"Posts returned: {len(data.get('results', []))}")
            
            # Show first post details
            if data.get('results'):
                first_post = data['results'][0]
                print(f"First post ID: {first_post.get('id')}")
                print(f"First post content: {first_post.get('content', '')[:50]}...")
        else:
            print(f"❌ Feed failed: {response.data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_feed()
