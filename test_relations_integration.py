import requests
import json
from pprint import pprint

# Your login credentials
login_url = "http://192.168.1.44:8002/api/admin/auth/login/"
login_data = {
    "full_name": "Your Name",  # Replace with your details
    "mobile_number": "your_number",
    "email": "your_email",
    "password": "your_password"
}

# First, login to get a fresh token
print("Logging in...")
login_response = requests.post(login_url, json=login_data)

if login_response.status_code == 200:
    token = login_response.json().get('access')
    print(f"✅ Login successful, got token")
    
    # Now try to create the override
    url = "http://192.168.1.44:8002/api/admin/profile-overrides/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    data = {
        "relation_code": "MOTHER",
        "language": "ta",
        "religion": "Hindu",
        "native": "Karaikudi",
        "present_city": "Chennai",
        "taluk": "Tirupattur",
        "district": "Sivagangai",
        "state": "Tamil Nadu",
        "nationality": "Indian",
        "label": "அம்மா (செட்டிநாடு)"
    }
    
    print("\nSending POST request to create override...")
    response = requests.post(url, headers=headers, json=data)
    
    print(f"\n🔹 Status Code: {response.status_code}")
    print(f"🔹 Response Headers: {dict(response.headers)}")
    
    try:
        print(f"🔹 Response Body:")
        pprint(response.json())
    except:
        print(f"🔹 Raw Response: {response.text}")
        
    # If 403, check permissions
    if response.status_code == 403:
        print("\n❌ Permission Denied! Checking your permissions...")
        
        # Check user permissions
        me_url = "http://192.168.1.44:8002/api/admin/profile/"
        me_response = requests.get(me_url, headers=headers)
        if me_response.status_code == 200:
            print("✅ Profile accessible")
            pprint(me_response.json())
        else:
            print(f"❌ Profile error: {me_response.status_code}")
            
else:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)