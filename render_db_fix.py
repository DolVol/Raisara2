#!/usr/bin/env python3
"""
Render Database Fix Script
This script is designed to run on Render to fix the missing user table columns.
"""

import os
import psycopg2
from urllib.parse import urlparse

def fix_user_table_on_render():
    """Fix user table columns on Render PostgreSQL database"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL environment variable not found")
        return False
    
    print("🔗 Connecting to Render PostgreSQL database...")
    
    try:
        # Parse the database URL
        parsed = urlparse(database_url)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:],  # Remove leading slash
            user=parsed.username,
            password=parsed.password
        )
        
        cursor = conn.cursor()
        
        print("✅ Connected to database")
        
        # Check current columns in user table
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user'
            ORDER BY column_name
        """)
        
        current_columns = [row[0] for row in cursor.fetchall()]
        print(f"📋 Current user table columns: {current_columns}")
        
        # Define required columns
        required_columns = {
            'last_login': 'TIMESTAMP',
            'previous_login': 'TIMESTAMP', 
            'login_count': 'INTEGER DEFAULT 0'
        }
        
        # Add missing columns
        columns_added = []
        for column_name, column_type in required_columns.items():
            if column_name not in current_columns:
                try:
                    sql = f'ALTER TABLE "user" ADD COLUMN {column_name} {column_type}'
                    print(f"🔧 Adding column: {sql}")
                    cursor.execute(sql)
                    conn.commit()
                    columns_added.append(column_name)
                    print(f"✅ Successfully added column: {column_name}")
                except Exception as col_error:
                    print(f"❌ Error adding column {column_name}: {col_error}")
                    conn.rollback()
                    return False
            else:
                print(f"✅ Column {column_name} already exists")
        
        # Verify columns were added
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'user' 
            AND column_name IN ('last_login', 'previous_login', 'login_count')
            ORDER BY column_name
        """)
        
        verification_results = cursor.fetchall()
        print("\n📋 Verification - User table columns:")
        for row in verification_results:
            print(f"   - {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
        
        cursor.close()
        conn.close()
        
        if columns_added:
            print(f"\n✅ Successfully added {len(columns_added)} columns: {columns_added}")
        else:
            print("\n✅ All required columns were already present")
        
        print("🎉 Database fix completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def main():
    """Main function"""
    print("🚀 Render Database Fix - User Table Columns")
    print("=" * 50)
    
    # Check if we're on Render
    if not os.getenv('RENDER'):
        print("⚠️  This script is designed to run on Render")
        print("💡 Make sure RENDER environment variable is set")
    
    success = fix_user_table_on_render()
    
    print("=" * 50)
    if success:
        print("✅ Database fix completed successfully!")
        print("🎉 Login and registration should now work")
    else:
        print("❌ Database fix failed")
        print("💡 Check the error messages above")
    
    return success

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)