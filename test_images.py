mport requests
import os
import json

def test_image_system():
    """Test the image upload and display system"""
    
    base_url = "http://127.0.0.1:5000"
    
    print("🧪 Testing Image Upload System")
    print("=" * 50)
    
    # Test 1: Check debug endpoint
    print("\n1️⃣ Checking image system status...")
    try:
        response = requests.get(f"{base_url}/debug/images")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Uploads folder: {data.get('uploads_folder')}")
            print(f"📁 Files in uploads: {len(data.get('files_in_uploads', []))}")
            print(f"🌳 Trees with images: {len(data.get('trees_with_images', []))}")
            print(f"🏠 Domes with images: {len(data.get('domes_with_images', []))}")
        else:
            print(f"❌ Debug endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking debug endpoint: {e}")
    
    # Test 2: Fix image system
    print("\n2️⃣ Fixing image system...")
    try:
        response = requests.post(f"{base_url}/debug/fix_images")
        if response.status_code == 200:
            print("✅ Image system fixed successfully")
        else:
            print(f"❌ Fix failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fixing image system: {e}")
    
    # Test 3: Check if we have any domes/trees to test with
    print("\n3️⃣ Checking available domes and trees...")
    try:
        response = requests.get(f"{base_url}/domes")
        if response.status_code == 200:
            domes = response.json()
            print(f"🏠 Found {len(domes)} domes")
            
            for dome in domes[:3]:  # Check first 3 domes
                dome_id = dome['id']
                response = requests.get(f"{base_url}/api/trees/{dome_id}")
                if response.status_code == 200:
                    trees_data = response.json()
                    trees = trees_data.get('trees', [])
                    print(f"  - Dome {dome_id} ({dome['name']}): {len(trees)} trees")
                    
                    # Show trees with images
                    trees_with_images = [t for t in trees if t.get('image_url')]
                    if trees_with_images:
                        print(f"    🖼️ Trees with images: {len(trees_with_images)}")
                        for tree in trees_with_images:
                            print(f"      - {tree['name']}: {tree['image_url']}")
        else:
            print(f"❌ Failed to get domes: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking domes/trees: {e}")
    
    # Test 4: Create a test image file
    print("\n4️⃣ Creating test image...")
    try:
        from PIL import Image
        import io
        
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='green')
        
        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        print("✅ Test image created (100x100 green square)")
        
        # If we have domes, try uploading to the first one
        response = requests.get(f"{base_url}/domes")
        if response.status_code == 200:
            domes = response.json()
            if domes:
                dome_id = domes[0]['id']
                print(f"📤 Attempting to upload test image to dome {dome_id}...")
                
                files = {'image': ('test.png', img_bytes, 'image/png')}
                response = requests.post(f"{base_url}/upload_dome_image/{dome_id}", files=files)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        print(f"✅ Upload successful: {result.get('image_url')}")
                        print(f"📁 File: {result.get('filename')}")
                        print(f"📏 Size: {result.get('file_size')} bytes")
                    else:
                        print(f"❌ Upload failed: {result.get('error')}")
                else:
                    print(f"❌ Upload request failed: {response.status_code}")
                    print(f"Response: {response.text}")
        
    except ImportError:
        print("⚠️ PIL not available, skipping image creation test")
        print("Install with: pip install Pillow")
    except Exception as e:
        print(f"❌ Error creating/uploading test image: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Image system test completed!")
    print("\nIf uploads are working:")
    print("1. Check the /uploads folder for saved files")
    print("2. Visit your Flask app and try uploading images")
    print("3. Images should appear in the grid after upload")

if __name__ == '__main__':
    test_image_system()