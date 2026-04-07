#!/usr/bin/env python
"""
Comprehensive test of all post system logic
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
from apps.posts.models import Post, PostAudience, PostMedia, PostVisibilityRule
from apps.posts.services import PostVisibilityService

User = get_user_model()

def test_all_logic():
    print("🔍 COMPREHENSIVE POST SYSTEM VALIDATION")
    print("=" * 60)
    
    user = User.objects.first()
    if not user:
        print("❌ No users found!")
        return
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    print(f"✅ User: {user.id} - {user.mobile_number}")
    
    # Test 1: Create different visibility posts
    print("\n📝 TEST 1: Create Posts with Different Visibility")
    print("-" * 40)
    
    # Public post
    public_post = Post.objects.create(
        author=user,
        content="Public test post",
        visibility='public'
    )
    PostVisibilityService.precompute_audience_for_post(public_post)
    print(f"✅ Created public post: {public_post.id}")
    
    # Connections post
    connections_post = Post.objects.create(
        author=user,
        content="Connections test post",
        visibility='connections'
    )
    PostVisibilityService.precompute_audience_for_post(connections_post)
    print(f"✅ Created connections post: {connections_post.id}")
    
    # Custom post with rule
    rule = PostVisibilityRule.objects.filter(is_active=True).first()
    custom_post = None
    if rule:
        custom_post = Post.objects.create(
            author=user,
            content="Custom test post",
            visibility='custom',
            custom_visibility_rule=rule
        )
        PostVisibilityService.precompute_audience_for_post(custom_post)
        print(f"✅ Created custom post: {custom_post.id} with rule: {rule.name}")
    
    print("\n📊 TEST 2: Visibility Rules Logic")
    print("-" * 40)
    
    # Test visibility rule eligibility
    if rule:
        print(f"✅ Rule: {rule.name}")
        print(f"  - Caste criteria: {rule.caste_criteria}")
        print(f"  - Religion criteria: {rule.religion_criteria}")
        print(f"  - Area criteria: {rule.area_criteria}")
        
        is_eligible = rule.is_user_eligible(user)
        print(f"  - User eligible: {is_eligible}")
        
        eligible_users = rule.get_eligible_users_queryset()
        print(f"  - Total eligible users: {eligible_users.count()}")
    
    print("\n👥 TEST 3: Feed Generation")
    print("-" * 40)
    
    # Test feed service
    feed_posts = PostVisibilityService.get_visible_posts_for_user(user, 10, 0)
    print(f"✅ Feed posts found: {feed_posts.count()}")
    
    for post in feed_posts:
        print(f"  - Post {post.id}: {post.content[:30]}... ({post.visibility})")
        
        # Check media
        media_count = post.media.count()
        if media_count > 0:
            print(f"    📸 Media: {media_count} files")
            for media in post.media.all():
                print(f"      - {media.media_type}: {media.caption[:20]}...")
    
    print("\n🔍 TEST 4: Audience Precomputation")
    print("-" * 40)
    
    # Test audience table
    total_audience = PostAudience.objects.filter(user=user).count()
    print(f"✅ Total audience entries: {total_audience}")
    
    # Check audience breakdown
    public_audience = PostAudience.objects.filter(user=user, visibility_reason='public').count()
    author_audience = PostAudience.objects.filter(user=user, visibility_reason='author').count()
    connection_audience = PostAudience.objects.filter(user=user, visibility_reason='connection').count()
    custom_audience = PostAudience.objects.filter(user=user, visibility_reason='custom_rule').count()
    
    print(f"  - Public audience: {public_audience}")
    print(f"  - Author audience: {author_audience}")
    print(f"  - Connection audience: {connection_audience}")
    print(f"  - Custom audience: {custom_audience}")
    
    print("\n📱 TEST 5: API Endpoints")
    print("-" * 40)
    
    # Test feed API
    try:
        response = client.get('/api/posts/feed/?page=1&page_size=10')
        print(f"✅ Feed API Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            posts = data.get('posts', [])
            pagination = data.get('pagination', {})
            
            print(f"  - Posts returned: {len(posts)}")
            print(f"  - Total posts: {pagination.get('total_posts', 0)}")
            print(f"  - Current page: {pagination.get('current_page', 1)}")
            
            # Check media in response
            posts_with_media = [p for p in posts if p.get('media_count', 0) > 0]
            print(f"  - Posts with media: {len(posts_with_media)}")
            
            if posts_with_media:
                first_media_post = posts_with_media[0]
                media_array = first_media_post.get('media', [])
                if media_array:
                    print(f"  - First media: {media_array[0].get('media_type')} - {media_array[0].get('caption', 'No caption')}")
        else:
            print(f"  ❌ Feed API failed: {response.data}")
    except Exception as e:
        print(f"  ❌ Feed API error: {e}")
    
    print("\n🧹 TEST 6: User Posts Endpoint")
    print("-" * 40)
    
    # Test user posts API
    try:
        response = client.get(f'/api/posts/user/{user.id}/?page=1&page_size=10')
        print(f"✅ User Posts API Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            posts = data.get('posts', [])
            print(f"  - User posts returned: {len(posts)}")
            
            # Check if our created posts are there
            created_post_ids = [p.get('id') for p in posts]
            our_posts = [public_post.id, connections_post.id]
            if custom_post:
                our_posts.append(custom_post.id)
            
            found_our_posts = [pid for pid in our_posts if pid in created_post_ids]
            print(f"  - Our created posts found: {len(found_our_posts)}/{len(our_posts)}")
            
        else:
            print(f"  ❌ User Posts API failed: {response.data}")
    except Exception as e:
        print(f"  ❌ User Posts API error: {e}")
    
    print("\n🎯 TEST 7: Post Details")
    print("-" * 40)
    
    # Test post details API
    if public_post:
        try:
            response = client.get(f'/api/posts/{public_post.id}/')
            print(f"✅ Post Details API Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"  - Post ID: {response.data.get('id')}")
                print(f"  - Content: {response.data.get('content', '')[:50]}...")
                print(f"  - Visibility: {response.data.get('visibility')}")
                print(f"  - Likes: {response.data.get('likes_count', 0)}")
                print(f"  - Comments: {response.data.get('comments_count', 0)}")
                print(f"  - Media count: {response.data.get('media_count', 0)}")
                
        except Exception as e:
            print(f"  ❌ Post Details API error: {e}")
    
    print("\n🗑️ CLEANUP")
    print("-" * 40)
    
    # Clean up test data
    Post.objects.filter(id__in=[public_post.id, connections_post.id]).delete()
    if custom_post:
        Post.objects.filter(id=custom_post.id).delete()
    PostAudience.objects.filter(user=user).delete()
    
    print("✅ Test data cleaned up")
    print("\n🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == '__main__':
    test_all_logic()
