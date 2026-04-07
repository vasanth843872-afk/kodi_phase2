#!/usr/bin/env python
"""
Debug script to find the exact source of the 'str' object has no attribute 'objects' error
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
from apps.posts.serializers import PostCreateSerializer
from apps.accounts.models import User

def test_serializer():
    print("Testing serializer...")
    
    # Get a user
    users = User.objects.all()[:1]
    if not users:
        print("No users found!")
        return
    
    user = users[0]
    print(f"Using user: {user.id} - {user.mobile_number}")
    
    # Create a visibility rule
    rule, created = PostVisibilityRule.objects.get_or_create(
        name='Test Rule for Debug',
        defaults={
            'description': 'Test rule for debugging',
            'caste_criteria': ['OC'],
            'religion_criteria': ['Hindu'],
            'is_active': True,
            'created_by': user
        }
    )
    
    print(f"Rule: {rule.id} - {rule.name}")
    
    # Test serializer with custom visibility
    data = {
        'content': 'Test post for debugging',
        'visibility': 'custom',
        'custom_visibility_rule': rule.id
    }
    
    print(f"Testing with data: {data}")
    
    try:
        serializer = PostCreateSerializer(data=data)
        print(f"Serializer valid: {serializer.is_valid()}")
        
        if not serializer.is_valid():
            print(f"Serializer errors: {serializer.errors}")
        else:
            print("Serializer validation passed!")
            
            # Try to save
            try:
                post = serializer.save(author=user)
                print(f"Post created: {post.id}")
                post.delete()
                print("Post deleted successfully")
            except Exception as e:
                print(f"Error saving post: {e}")
                import traceback
                traceback.print_exc()
                
    except Exception as e:
        print(f"Error creating serializer: {e}")
        import traceback
        traceback.print_exc()

def test_rule_methods():
    print("\nTesting rule methods...")
    
    rule = PostVisibilityRule.objects.first()
    if not rule:
        print("No visibility rules found!")
        return
    
    print(f"Testing rule: {rule.id} - {rule.name}")
    
    user = User.objects.first()
    if not user:
        print("No users found!")
        return
    
    print(f"Testing with user: {user.id} - {user.mobile_number}")
    
    try:
        # Test is_user_eligible
        eligible = rule.is_user_eligible(user)
        print(f"User eligible: {eligible}")
    except Exception as e:
        print(f"Error in is_user_eligible: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        # Test get_eligible_users_queryset
        queryset = rule.get_eligible_users_queryset()
        print(f"Eligible users queryset: {queryset.count()} users")
    except Exception as e:
        print(f"Error in get_eligible_users_queryset: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_serializer()
    test_rule_methods()
