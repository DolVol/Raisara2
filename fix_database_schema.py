#!/usr/bin/env python3
"""
Database Schema Fix Script
This script adds missing columns to your existing database
"""

import sqlite3
import os
from datetime import datetime

def fix_database_schema():
    """Fix missing columns in the database"""
    db_file = 'db.sqlite3'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return False
    
    print("🔧 Fixing database schema...")
    print("=" * 50)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Check current schema
        print("📋 Checking current database schema...")
        
        # Check grid_settings table
        cursor.execute("PRAGMA table_info(grid_settings);")
        grid_columns = [row[1] for row in cursor.fetchall()]
        print(f"grid_settings columns: {grid_columns}")
        
        # Check dome table  
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns = [row[1] for row in cursor.fetchall()]
        print(f"dome columns: {dome_columns}")
        
        # Check tree table
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns = [row[1] for row in cursor.fetchall()]
        print(f"tree columns: {tree_columns}")
        
        print("\n🔧 Adding missing columns...")
        
        # Fix grid_settings table
        if 'user_id' not in grid_columns:
            print("➕ Adding user_id column to grid_settings...")
            cursor.execute("ALTER TABLE grid_settings ADD COLUMN user_id INTEGER;")
            print("✅ Added user_id to grid_settings")
        else:
            print("✅ grid_settings.user_id already exists")
        
        # Fix dome table
        missing_dome_columns = []
        
        if 'farm_id' not in dome_columns:
            missing_dome_columns.append('farm_id')
            cursor.execute("ALTER TABLE dome ADD COLUMN farm_id INTEGER;")
            print("✅ Added farm_id to dome")
        
        if 'created_at' not in dome_columns:
            missing_dome_columns.append('created_at')
            cursor.execute("ALTER TABLE dome ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at to dome")
        
        if 'updated_at' not in dome_columns:
            missing_dome_columns.append('updated_at')
            cursor.execute("ALTER TABLE dome ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at to dome")
        
        if not missing_dome_columns:
            print("✅ dome table already has all required columns")
        
        # Fix tree table
        missing_tree_columns = []
        
        if 'created_at' not in tree_columns:
            missing_tree_columns.append('created_at')
            cursor.execute("ALTER TABLE tree ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at to tree")
        
        if 'updated_at' not in tree_columns:
            missing_tree_columns.append('updated_at')
            cursor.execute("ALTER TABLE tree ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at to tree")
        
        if not missing_tree_columns:
            print("✅ tree table already has all required columns")
        
        # Create farm table if it doesn't exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm';")
        if not cursor.fetchone():
            print("➕ Creating farm table...")
            cursor.execute('''
                CREATE TABLE farm (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    grid_row INTEGER NOT NULL,
                    grid_col INTEGER NOT NULL,
                    image_url VARCHAR(255),
                    user_id INTEGER NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES user(id)
                )
            ''')
            print("✅ Created farm table")
        else:
            print("✅ farm table already exists")
        
        # Update existing records with default timestamps
        current_time = datetime.utcnow().isoformat()
        
        # Update dome records
        cursor.execute("UPDATE dome SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_domes = cursor.rowcount
        if updated_domes > 0:
            print(f"✅ Updated {updated_domes} dome records with timestamps")
        
        # Update tree records
        cursor.execute("UPDATE tree SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_trees = cursor.rowcount
        if updated_trees > 0:
            print(f"✅ Updated {updated_trees} tree records with timestamps")
        
        # Commit all changes
        conn.commit()
        print("\n🎉 Database schema fixed successfully!")
        
        # Verify the fixes
        print("\n🔍 Verifying fixes...")
        
        # Check grid_settings again
        cursor.execute("PRAGMA table_info(grid_settings);")
        grid_columns_after = [row[1] for row in cursor.fetchall()]
        
        # Check dome again
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns_after = [row[1] for row in cursor.fetchall()]
        
        # Check tree again
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns_after = [row[1] for row in cursor.fetchall()]
        
        print(f"✅ grid_settings columns: {grid_columns_after}")
        print(f"✅ dome columns: {dome_columns_after}")
        print(f"✅ tree columns: {tree_columns_after}")
        
        # Check if all required columns exist
        required_checks = [
            ('grid_settings', 'user_id', 'user_id' in grid_columns_after),
            ('dome', 'farm_id', 'farm_id' in dome_columns_after),
            ('dome', 'created_at', 'created_at' in dome_columns_after),
            ('dome', 'updated_at', 'updated_at' in dome_columns_after),
            ('tree', 'created_at', 'created_at' in tree_columns_after),
            ('tree', 'updated_at', 'updated_at' in tree_columns_after),
        ]
        
        all_good = True
        for table, column, exists in required_checks:
            if exists:
                print(f"✅ {table}.{column} exists")
            else:
                print(f"❌ {table}.{column} missing")
                all_good = False
        
        if all_good:
            print("\n🎉 All required columns are now present!")
            print("\nYour app should now work without schema errors.")
            print("\nNext steps:")
            print("1. Restart your Flask app: python app.py")
            print("2. Test the application")
            return True
        else:
            print("\n❌ Some columns are still missing")
            return False
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_upload_directories():
    """Create necessary upload directories"""
    print("\n📁 Creating upload directories...")
    
    directories = [
        'uploads',
        'uploads/trees',
        'uploads/domes', 
        'uploads/farms'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def main():
    """Main function"""
    print("🚀 Database Schema Fix Tool")
    print("=" * 50)
    
    if fix_database_schema():
        create_upload_directories()
        print("\n" + "=" * 50)
        print("🎉 Database fix completed successfully!")
        print("\nYour Flask app should now work without schema errors.")
        print("You can now run: python app.py")
    else:
        print("\n" + "=" * 50)
        print("❌ Database fix failed!")
        print("Please check the errors above and try again.")

if __name__ == '__main__':
    main()