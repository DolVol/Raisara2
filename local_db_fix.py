#!/usr/bin/env python3
"""
Local Database Fix - For testing locally with SQLite
This script adds missing columns to your local SQLite database.
"""

import sqlite3
import os

def fix_local_database():
    """Fix missing user table columns in local SQLite database"""
    
    db_path = "db.sqlite3"
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found")
        return False
    
    print(f"🔗 Connecting to local database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("✅ Connected to local SQLite database")
        
        # Check current columns
        cursor.execute("PRAGMA table_info(user)")
        current_columns = [row[1] for row in cursor.fetchall()]
        print(f"📋 Current user table columns: {current_columns}")
        
        # Add missing columns
        columns_to_add = [
            ("last_login", "DATETIME"),
            ("previous_login", "DATETIME"),
            ("login_count", "INTEGER DEFAULT 0")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in current_columns:
                try:
                    sql = f"ALTER TABLE user ADD COLUMN {column_name} {column_type}"
                    print(f"🔧 Adding: {sql}")
                    cursor.execute(sql)
                    conn.commit()
                    print(f"✅ Added column: {column_name}")
                except Exception as e:
                    print(f"❌ Error adding column {column_name}: {e}")
                    return False
            else:
                print(f"✅ Column {column_name} already exists")
        
        # Verify columns were added
        cursor.execute("PRAGMA table_info(user)")
        updated_columns = [row[1] for row in cursor.fetchall()]
        print(f"📋 Updated user table columns: {updated_columns}")
        
        required_columns = ['last_login', 'previous_login', 'login_count']
        if all(col in updated_columns for col in required_columns):
            print("🎉 SUCCESS! All required columns are now present locally")
            return True
        else:
            missing = [col for col in required_columns if col not in updated_columns]
            print(f"❌ Still missing columns: {missing}")
            return False
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Local Database Fix for User Table")
    print("=" * 40)
    success = fix_local_database()
    print("=" * 40)
    if success:
        print("✅ Local fix completed!")
        print("💡 Now run the same fix on Render using quick_db_fix.py")
    else:
        print("❌ Local fix failed. Check errors above.")