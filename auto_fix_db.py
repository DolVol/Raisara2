#!/usr/bin/env python3
"""
Auto Database Fix - Runs automatically on app startup
This script fixes the missing user table columns automatically when the app starts.
"""

import os
import psycopg2
from urllib.parse import urlparse

def auto_fix_user_table():
    """Automatically fix missing user table columns on startup"""
    
    # Only run on Render (production)
    if not os.getenv('RENDER'):
        print("ℹ️ Auto-fix skipped (not on Render)")
        return True
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("⚠️ DATABASE_URL not found, skipping auto-fix")
        return False
    
    print("🔧 Auto-fixing user table columns...")
    
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
        
        # Check if columns exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user' 
            AND column_name IN ('last_login', 'previous_login', 'login_count')
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        required_columns = ['last_login', 'previous_login', 'login_count']
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        if not missing_columns:
            print("✅ All user table columns already exist")
            cursor.close()
            conn.close()
            return True
        
        print(f"🔧 Adding missing columns: {missing_columns}")
        
        # Add missing columns
        column_definitions = {
            'last_login': 'TIMESTAMP',
            'previous_login': 'TIMESTAMP',
            'login_count': 'INTEGER DEFAULT 0'
        }
        
        for column_name in missing_columns:
            try:
                column_type = column_definitions[column_name]
                sql = f'ALTER TABLE "user" ADD COLUMN {column_name} {column_type}'
                cursor.execute(sql)
                conn.commit()
                print(f"✅ Added column: {column_name}")
            except Exception as col_error:
                print(f"❌ Error adding column {column_name}: {col_error}")
                conn.rollback()
                cursor.close()
                conn.close()
                return False
        
        # Verify all columns now exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user' 
            AND column_name IN ('last_login', 'previous_login', 'login_count')
        """)
        
        final_columns = [row[0] for row in cursor.fetchall()]
        
        if len(final_columns) == 3:
            print("🎉 Auto-fix completed successfully! Login/registration should now work.")
            cursor.close()
            conn.close()
            return True
        else:
            print(f"❌ Auto-fix incomplete. Found columns: {final_columns}")
            cursor.close()
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ Auto-fix error: {e}")
        return False

if __name__ == "__main__":
    auto_fix_user_table()