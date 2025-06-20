#!/usr/bin/env python3
"""
Quick Database Fix - Run this in Render Shell
This script directly adds the missing columns to fix the login issue immediately.
"""

import os
import psycopg2
from urllib.parse import urlparse

def quick_fix():
    """Quick fix for missing user table columns"""
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    print("🔗 Connecting to database...")
    
    try:
        # Parse database URL
        parsed = urlparse(database_url)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:],
            user=parsed.username,
            password=parsed.password
        )
        
        cursor = conn.cursor()
        print("✅ Connected to database")
        
        # Add missing columns one by one
        columns_to_add = [
            ("last_login", "TIMESTAMP"),
            ("previous_login", "TIMESTAMP"),
            ("login_count", "INTEGER DEFAULT 0")
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                # Check if column exists
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'user' AND column_name = %s
                """, (column_name,))
                
                if cursor.fetchone():
                    print(f"✅ Column {column_name} already exists")
                else:
                    # Add the column
                    sql = f'ALTER TABLE "user" ADD COLUMN {column_name} {column_type}'
                    print(f"🔧 Adding: {sql}")
                    cursor.execute(sql)
                    conn.commit()
                    print(f"✅ Added column: {column_name}")
                    
            except Exception as e:
                print(f"❌ Error with column {column_name}: {e}")
                conn.rollback()
        
        # Verify all columns exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user' 
            AND column_name IN ('last_login', 'previous_login', 'login_count')
            ORDER BY column_name
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"📋 User table now has columns: {existing_columns}")
        
        required_columns = ['last_login', 'login_count', 'previous_login']
        if all(col in existing_columns for col in required_columns):
            print("🎉 SUCCESS! All required columns are now present")
            print("🚀 Login and registration should now work!")
            return True
        else:
            missing = [col for col in required_columns if col not in existing_columns]
            print(f"❌ Still missing columns: {missing}")
            return False
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Quick Database Fix for User Table")
    print("=" * 40)
    success = quick_fix()
    print("=" * 40)
    if success:
        print("✅ Fix completed! Try logging in now.")
    else:
        print("❌ Fix failed. Check errors above.")