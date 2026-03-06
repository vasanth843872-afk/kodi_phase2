#!/usr/bin/env python3
"""
Test script for the new invitation with relationship path endpoint
"""

import requests
import json

# Configuration
BASE_URL = "http://192.168.1.13:8002"
TOKEN = "your_jwt_token_here"  # Replace with actual token

def test_invitation_with_path():
    """Test the new invitation with path endpoint"""
    
    # Test endpoint
    invitation_id = 1  # Replace with actual invitation ID
    url = f"{BASE_URL}/api/genealogy/invitations/{invitation_id}/view-with-path/"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Success! Invitation with relationship path:")
            print(f"Message: {data.get('message', 'N/A')}")
            print(f"Path String: {data['relationship_path']['path_string']}")
            print(f"Total Steps: {data['relationship_path']['total_steps']}")
            
            # Show visual path
            print("\n📍 Visual Path:")
            for step in data.get('path_visual', []):
                person_name = step['person']['name']
                relation_label = step['relation']['label']
                profile_pic = step['person'].get('profile_picture', 'No picture')
                print(f"  Step {step['step']}: {person_name} ({relation_label}) - {profile_pic}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {str(e)}")

def test_regular_invitation():
    """Test the regular invitation endpoint for comparison"""
    
    invitation_id = 1
    url = f"{BASE_URL}/api/genealogy/invitations/{invitation_id}/"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Regular invitation endpoint:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {str(e)}")

if __name__ == "__main__":
    print("🧪 Testing Invitation Relationship Path Feature")
    print("=" * 50)
    
    print("\n1. Testing regular invitation endpoint:")
    test_regular_invitation()
    
    print("\n2. Testing invitation WITH relationship path:")
    test_invitation_with_path()
    
    print("\n" + "=" * 50)
    print("📝 Usage:")
    print("GET /api/genealogy/invitations/{id}/view-with-path/")
    print("Headers: Authorization: Bearer <token>")
