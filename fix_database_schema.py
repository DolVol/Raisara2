import sqlite3
import os
from flask import Flask
from models import db, Dome, Tree

def fix_database_schema():
    """Fix database schema to ensure image columns exist"""
    
    print("🔧 Fixing database schema...")
    
    # Connect directly to SQLite database
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        # Check current dome table structure
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Current dome columns: {dome_columns}")
        
        # Add image_url to dome table if missing
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
        
        # Commit changes
        conn.commit()
        print("✅ Database schema updated successfully!")
        
        # Verify uploads folder exists
        if not os.path.exists('uploads'):
            os.makedirs('uploads')
            print("✅ Created uploads folder")
        else:
            print("ℹ️ Uploads folder already exists")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing database schema: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def verify_database():
    """Verify database structure"""
    print("\n🔍 Verifying database structure...")
    
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        # Check dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = cursor.fetchall()
        print("\n📋 Dome table structure:")
        for col in dome_columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check tree table
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = cursor.fetchall()
        print("\n🌳 Tree table structure:")
        for col in tree_columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check for existing images
        cursor.execute("SELECT id, name, image_url FROM tree WHERE image_url IS NOT NULL")
        trees_with_images = cursor.fetchall()
        print(f"\n🖼️ Trees with images: {len(trees_with_images)}")
        for tree in trees_with_images:
            print(f"  - Tree {tree[0]} ({tree[1]}): {tree[2]}")
        
        cursor.execute("SELECT id, name, image_url FROM dome WHERE image_url IS NOT NULL")
        domes_with_images = cursor.fetchall()
        print(f"\n🏠 Domes with images: {len(domes_with_images)}")
        for dome in domes_with_images:
            print(f"  - Dome {dome[0]} ({dome[1]}): {dome[2]}")
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Database Schema Fixer ===")
    
    # Fix schema
    if fix_database_schema():
        # Verify the fix
        verify_database()
        print("\n🎉 Database schema fix completed!")
        print("\nNext steps:")
        print("1. Restart your Flask app")
        print("2. Try uploading images again")
        print("3. Check if images appear in the grid")
    else:
        print("\n❌ Failed to fix database schema")