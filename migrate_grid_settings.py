"""
Migration script to update GridSettings table with new columns
Run this once to fix the database schema
"""

import os
import sqlite3
from datetime import datetime

def migrate_grid_settings():
    """Add missing columns to grid_settings table"""
    try:
        # Connect to the database
        db_path = 'db.sqlite3'
        if not os.path.exists(db_path):
            print("❌ Database file not found!")
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Starting GridSettings migration...")
        
        # Check current table structure
        cursor.execute("PRAGMA table_info(grid_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        # Add grid_type column if it doesn't exist
        if 'grid_type' not in columns:
            print("Adding grid_type column...")
            cursor.execute("ALTER TABLE grid_settings ADD COLUMN grid_type VARCHAR(20) DEFAULT 'dome'")
            print("✅ Added grid_type column")
        
        # Add user_id column if it doesn't exist
        if 'user_id' not in columns:
            print("Adding user_id column...")
            cursor.execute("ALTER TABLE grid_settings ADD COLUMN user_id INTEGER")
            print("✅ Added user_id column")
        
        # Add created_at column if it doesn't exist
        if 'created_at' not in columns:
            print("Adding created_at column...")
            cursor.execute("ALTER TABLE grid_settings ADD COLUMN created_at DATETIME")
            print("✅ Added created_at column")
        
        # Add updated_at column if it doesn't exist
        if 'updated_at' not in columns:
            print("Adding updated_at column...")
            cursor.execute("ALTER TABLE grid_settings ADD COLUMN updated_at DATETIME")
            print("✅ Added updated_at column")
        
        # Update existing records
        print("Updating existing records...")
        
        # Set default values for existing records
        current_time = datetime.utcnow().isoformat()
        
        # Update grid_type for existing records
        cursor.execute("UPDATE grid_settings SET grid_type = 'dome' WHERE grid_type IS NULL")
        
        # Get the first user ID to assign to existing settings
        cursor.execute("SELECT id FROM user LIMIT 1")
        first_user = cursor.fetchone()
        
        if first_user:
            user_id = first_user[0]
            cursor.execute("UPDATE grid_settings SET user_id = ? WHERE user_id IS NULL", (user_id,))
            print(f"✅ Assigned existing settings to user {user_id}")
        
        # Set timestamps for existing records
        cursor.execute("UPDATE grid_settings SET created_at = ? WHERE created_at IS NULL", (current_time,))
        cursor.execute("UPDATE grid_settings SET updated_at = ? WHERE updated_at IS NULL", (current_time,))
        
        # Commit all changes
        conn.commit()
        
        # Verify migration
        cursor.execute("PRAGMA table_info(grid_settings)")
        new_columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ Migration completed! New columns: {new_columns}")
        
        # Show current data
        cursor.execute("SELECT * FROM grid_settings")
        records = cursor.fetchall()
        print(f"Current records: {len(records)}")
        for record in records:
            print(f"  - ID: {record[0]}, Rows: {record[1]}, Cols: {record[2]}")
            if len(record) > 3:
                print(f"    Type: {record[3]}, User: {record[4]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("GridSettings Migration Tool")
    print("=" * 40)
    
    success = migrate_grid_settings()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("You can now restart your Flask app.")
        print("The grid settings should work properly now.")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above.")