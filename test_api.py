#!/usr/bin/env python
"""
Test script to verify post creation API works correctly
"""
import requests
import json

def test_post_api():
    print("Testing post creation API...")
    
    # First, get auth token (you'll need to replace with actual credentials)
    login_data = {
        "mobile_number": "3333333333",  # Replace with actual user
        "otp": "123456"  # Replace with actual OTP or use your auth method
    }
    
    try:
        # Login to get token
        login_response = requests.post(
            "http://localhost:8000/api/auth/login/",
            json=login_data
        )
        
        if login_response.status_code == 200:
            token_data = login_response.json()
            access_token = token_data.get('access')
            print("Successfully logged in")
        else:
            print(f"Login failed: {login_response.status_code} - {login_response.text}")
            return
        
        # Test post creation with simple content (no custom visibility)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        post_data = {
            "content": "This is a test post created via API",
            "visibility": "connections"  # Use default visibility
        }
        
        print("Creating post with connections visibility...")
        post_response = requests.post(
            "http://localhost:8000/api/posts/create/",
            json=post_data,
            headers=headers
        )
        
        print(f"Post creation response: {post_response.status_code}")
        print(f"Response data: {post_response.text}")
        
        if post_response.status_code == 201:
            print("✅ Post created successfully!")
            post_data = post_response.json()
            print(f"Post ID: {post_data.get('id')}")
        else:
            print("❌ Post creation failed")
        
        # Test with custom visibility (if rule exists)
        custom_post_data = {
            "content": "This is a test post with custom visibility",
            "visibility": "custom",
            "custom_visibility_rule": 1  # Use rule ID 1
        }
        
        print("\nCreating post with custom visibility...")
        custom_response = requests.post(
            "http://localhost:8000/api/posts/create/",
            json=custom_post_data,
            headers=headers
        )
        
        print(f"Custom post response: {custom_response.status_code}")
        print(f"Response data: {custom_response.text}")
        
        if custom_response.status_code == 201:
            print("✅ Custom visibility post created successfully!")
        else:
            print("❌ Custom visibility post creation failed")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the server. Make sure Django server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_post_api()
