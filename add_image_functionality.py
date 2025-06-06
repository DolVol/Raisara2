import sqlite3
import os
import sys

def add_image_functionality():
    """Add image functionality to existing database"""
    
    # Check if database exists, if not, create it first
    if not os.path.exists('db.sqlite3'):
        print("❌ Database not found!")
        print("🔄 Creating database first...")
        
        # Try to create database by importing and running the app briefly
        try:
            # Import the app to trigger database creation
            from app import app
            with app.app_context():
                from models import db
                db.create_all()
                print("✅ Database created successfully")
        except Exception as e:
            print(f"❌ Error creating database: {e}")
            print("\n💡 Please run 'python app.py' first to create the database, then run this script again.")
            return False
    
    try:
        print("🔄 Adding image functionality to existing database...")
        
        # Connect to database
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # Check current dome table structure
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Current dome columns: {dome_columns}")
        
        # Add image_url to dome table if it doesn't exist
        if 'image_url' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
            print("✅ Added image_url column to dome table")
        else:
            print("ℹ️ image_url already exists in dome table")
        
        # Check current tree table structure
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"Current tree columns: {tree_columns}")
        
        # Add missing columns to tree table
        if 'image_url' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
            print("✅ Added image_url column to tree table")
        else:
            print("ℹ️ image_url already exists in tree table")
            
        if 'info' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
            print("✅ Added info column to tree table")
        else:
            print("ℹ️ info already exists in tree table")
            
        if 'life_days' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
            print("✅ Added life_days column to tree table")
        else:
            print("ℹ️ life_days already exists in tree table")
        
        # Create uploads folder
        if not os.path.exists('uploads'):
            os.makedirs('uploads')
            print("✅ Created uploads folder")
        else:
            print("ℹ️ Uploads folder already exists")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("\n🎉 Image functionality added successfully!")
        print("\nNext steps:")
        print("1. Update your models.py (uncomment image_url lines)")
        print("2. Update your app.py (add image upload routes)")
        print("3. Install required libraries: pip install qrcode[pil] Pillow")
        print("4. Restart your Flask app")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding image functionality: {e}")
        return False

def verify_database():
    """Verify database structure"""
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("\n🔍 Current database structure:")
        
        # Check all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"Tables: {[table[0] for table in tables]}")
        
        # Check dome table
        if any('dome' in table for table in tables):
            cursor.execute("PRAGMA table_info(dome)")
            dome_columns = [column[1] for column in cursor.fetchall()]
            print(f"Dome columns: {dome_columns}")
        
        # Check tree table
        if any('tree' in table for table in tables):
            cursor.execute("PRAGMA table_info(tree)")
            tree_columns = [column[1] for column in cursor.fetchall()]
            print(f"Tree columns: {tree_columns}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

if __name__ == '__main__':
    print("=== Database Image Functionality Setup ===")
    print("Choose an option:")
    print("1. Add image functionality to database")
    print("2. Verify current database structure")
    print("3. Both (verify then add)")
    
    choice = input("Enter your choice (1, 2, or 3): ").strip()
    
    if choice == "1":
        add_image_functionality()
    elif choice == "2":
        verify_database()
    elif choice == "3":
        verify_database()
        print("\n" + "="*50)
        add_image_functionality()
    else:
        print("Invalid choice. Please run the script again.")