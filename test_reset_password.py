#!/usr/bin/env python3
"""
Test script for password reset functionality
"""

import requests
import json

def test_reset_password():
    """Test the reset password endpoint"""
    
    # Test data
    test_data = {
        'token': 'test_token_123',
        'new_password': 'newpassword123',
        'confirm_password': 'newpassword123'
    }
    
    print("🧪 Testing reset password endpoint...")
    print(f"📤 Sending data: {test_data}")
    
    try:
        # Test POST request to reset password endpoint
        response = requests.post(
            'http://localhost:5000/reset_password',
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response data: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Password reset successful!")
            else:
                print(f"❌ Password reset failed: {result.get('error')}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - make sure the Flask server is running")
    except Exception as e:
        print(f"❌ Test error: {e}")

def test_missing_fields():
    """Test with missing required fields"""
    
    print("\n🧪 Testing with missing token...")
    
    test_data = {
        'new_password': 'newpassword123',
        'confirm_password': 'newpassword123'
    }
    
    try:
        response = requests.post(
            'http://localhost:5000/reset_password',
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response data: {response.text}")
        
        if response.status_code == 400:
            result = response.json()
            if 'Token and password are required' in result.get('error', ''):
                print("✅ Correctly rejected missing token!")
            else:
                print(f"❌ Unexpected error message: {result.get('error')}")
        else:
            print(f"❌ Expected 400 status, got {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - make sure the Flask server is running")
    except Exception as e:
        print(f"❌ Test error: {e}")

def test_password_mismatch():
    """Test with mismatched passwords"""
    
    print("\n🧪 Testing with mismatched passwords...")
    
    test_data = {
        'token': 'test_token_123',
        'new_password': 'newpassword123',
        'confirm_password': 'differentpassword'
    }
    
    try:
        response = requests.post(
            'http://localhost:5000/reset_password',
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response data: {response.text}")
        
        if response.status_code == 400:
            result = response.json()
            if 'Passwords do not match' in result.get('error', ''):
                print("✅ Correctly rejected mismatched passwords!")
            else:
                print(f"❌ Unexpected error message: {result.get('error')}")
        else:
            print(f"❌ Expected 400 status, got {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - make sure the Flask server is running")
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == '__main__':
    print("🔧 Password Reset Functionality Test")
    print("=" * 50)
    
    test_reset_password()
    test_missing_fields()
    test_password_mismatch()
    
    print("\n" + "=" * 50)
    print("🏁 Test completed!")
    print("\nTo run the Flask server:")
    print("cd c:\\chingunja && python app.py")