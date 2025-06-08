#!/usr/bin/env python3
"""
Database Update Script - Add Farm Support
"""

import sqlite3
import os
from datetime import datetime

def update_database():
    """Update database to add farm support"""
    db_file = 'db.sqlite3'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return False
    
    print("🔧 Updating database to add farm support...")
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Check current dome table structure
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns = [row[1] for row in cursor.fetchall()]
        print(f"Current dome columns: {dome_columns}")
        
        # Add missing columns to dome table
        if 'farm_id' not in dome_columns:
            print("➕ Adding farm_id column to dome table...")
            cursor.execute("ALTER TABLE dome ADD COLUMN farm_id INTEGER;")
            print("✅ Added farm_id column")
        else:
            print("✅ farm_id column already exists")
        
        if 'created_at' not in dome_columns:
            print("➕ Adding created_at column to dome table...")
            cursor.execute("ALTER TABLE dome ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at column")
        else:
            print("✅ created_at column already exists")
        
        if 'updated_at' not in dome_columns:
            print("➕ Adding updated_at column to dome table...")
            cursor.execute("ALTER TABLE dome ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at column")
        else:
            print("✅ updated_at column already exists")
        
        # Check if farm table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm';")
        farm_exists = cursor.fetchone()
        
        if not farm_exists:
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
        
        # Check tree table
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns = [row[1] for row in cursor.fetchall()]
        
        if 'created_at' not in tree_columns:
            print("➕ Adding created_at column to tree table...")
            cursor.execute("ALTER TABLE tree ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at to tree table")
        
        if 'updated_at' not in tree_columns:
            print("➕ Adding updated_at column to tree table...")
            cursor.execute("ALTER TABLE tree ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at to tree table")
        
        # Update existing records with default timestamps
        current_time = datetime.utcnow().isoformat()
        
        # Update dome records that don't have timestamps
        cursor.execute("UPDATE dome SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_domes = cursor.rowcount
        if updated_domes > 0:
            print(f"✅ Updated {updated_domes} dome records with timestamps")
        
        # Update tree records that don't have timestamps
        cursor.execute("UPDATE tree SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_trees = cursor.rowcount
        if updated_trees > 0:
            print(f"✅ Updated {updated_trees} tree records with timestamps")
        
        # Commit all changes
        conn.commit()
        print("🎉 Database update completed successfully!")
        
        # Verify the changes
        print("\n🔍 Verifying database structure...")
        
        # Check dome table
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns_after = [row[1] for row in cursor.fetchall()]
        print(f"Dome columns after update: {dome_columns_after}")
        
        # Check if all required columns exist
        required_columns = ['farm_id', 'created_at', 'updated_at']
        missing_columns = [col for col in required_columns if col not in dome_columns_after]
        
        if missing_columns:
            print(f"❌ Still missing columns: {missing_columns}")
            return False
        else:
            print("✅ All required columns are present")
            return True
        
    except Exception as e:
        print(f"❌ Error updating database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_upload_directories():
    """Create necessary upload directories"""
    print("\n📁 Creating upload directories...")
    
    directories = [
        'uploads/farms',
        'uploads/domes', 
        'uploads/trees'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def main():
    """Main function"""
    print("🚜 Database Update Script - Adding Farm Support")
    print("=" * 60)
    
    # Update database
    if update_database():
        # Create upload directories
        create_upload_directories()
        
        print("\n" + "=" * 60)
        print("🎉 Database update completed successfully!")
        print("\nChanges made:")
        print("✅ Added farm_id column to dome table")
        print("✅ Added created_at/updated_at columns to dome and tree tables")
        print("✅ Created farm table")
        print("✅ Created upload directories")
        print("\nNext steps:")
        print("1. Start your Flask app: python app.py")
        print("2. Go to http://192.168.1.38:5000/login")
        print("3. Test the farm system!")
        print("=" * 60)
    else:
        print("\n❌ Database update failed!")
        print("Please check the errors above and try again.")

if __name__ == '__main__':
    main()