#!/usr/bin/env python
"""
Test script to verify post creation works correctly
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from apps.posts.models import PostVisibilityRule, Post
from apps.accounts.models import User
from apps.profiles.models import UserProfile

def test_post_creation():
    print("Testing post creation...")
    
    # Check existing users
    users = User.objects.all()[:3]
    if not users:
        print("No users found. Please create some users first.")
        return
    
    user = users[0]
    print(f"Using user: {user.id} - {user.mobile_number}")
    
    # Check if user has a profile
    try:
        profile = user.profile
        print(f"User profile exists: {profile}")
    except UserProfile.DoesNotExist:
        print("User profile does not exist. Creating one...")
        profile = UserProfile.objects.create(
            user=user,
            firstname="Test",
            caste="OC",
            religion="Hindu",
            present_city="Chennai"
        )
        print(f"Created profile: {profile}")
    
    # Create a test visibility rule
    rule, created = PostVisibilityRule.objects.get_or_create(
        name='Test Rule',
        defaults={
            'description': 'Test rule for debugging',
            'caste_criteria': ['OC', 'BC'],
            'religion_criteria': ['Hindu'],
            'is_active': True,
            'created_by': user
        }
    )
    
    if created:
        print(f"Created rule: {rule.id} - {rule.name}")
    else:
        print(f"Using existing rule: {rule.id} - {rule.name}")
    
    # Test rule eligibility
    is_eligible = rule.is_user_eligible(user)
    print(f"User is eligible for rule: {is_eligible}")
    
    # Create a test post
    try:
        post = Post.objects.create(
            author=user,
            content="This is a test post with custom visibility",
            visibility='custom',
            custom_visibility_rule=rule
        )
        print(f"Created post: {post.id}")
        
        # Test visibility check
        can_view = post.get_visible_to_user(user)
        print(f"Author can view post: {can_view}")
        
        # Clean up
        post.delete()
        print("Test post deleted successfully")
        
    except Exception as e:
        print(f"Error creating post: {e}")
        import traceback
        traceback.print_exc()
    
    print("Test completed!")

if __name__ == '__main__':
    test_post_creation()
