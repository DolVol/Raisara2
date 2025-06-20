#!/usr/bin/env python3
"""
Complete Database Fix - Fixes all missing columns across all tables
This script fixes missing columns in user, farm, and tree tables.
"""

import os
import psycopg2
from urllib.parse import urlparse

def complete_database_fix():
    """Fix all missing columns in all tables"""
    
    # Only run on Render (production)
    if not os.getenv('RENDER'):
        print("ℹ️ Complete DB fix skipped (not on Render)")
        return True
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("⚠️ DATABASE_URL not found, skipping complete fix")
        return False
    
    print("🔧 Running complete database fix...")
    
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
        
        # Define all missing columns for each table
        table_fixes = {
            'user': [
                ('last_login', 'TIMESTAMP'),
                ('previous_login', 'TIMESTAMP'),
                ('login_count', 'INTEGER DEFAULT 0')
            ],
            'farm': [
                ('password_hash', 'VARCHAR(200)'),
                ('reset_token', 'VARCHAR(100)'),
                ('reset_token_expires', 'TIMESTAMP')
            ],
            'tree': [
                ('breed', 'VARCHAR(100)'),
                ('paste_metadata', 'TEXT'),
                ('life_day_offset', 'INTEGER DEFAULT 0'),
                ('is_paused', 'BOOLEAN DEFAULT FALSE'),
                ('paused_at', 'TIMESTAMP'),
                ('total_paused_days', 'INTEGER DEFAULT 0'),
                ('plant_type', 'VARCHAR(20) DEFAULT \'mother\''),
                ('cutting_notes', 'TEXT'),
                ('mother_plant_id', 'INTEGER'),
                ('planted_date', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            ]
        }
        
        total_columns_added = 0
        
        for table_name, columns in table_fixes.items():
            print(f"\n🔧 Checking table: {table_name}")
            
            # Get existing columns
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s
            """, (table_name,))
            
            existing_columns = [row[0] for row in cursor.fetchall()]
            print(f"📋 Existing columns in {table_name}: {existing_columns}")
            
            # Add missing columns
            for column_name, column_type in columns:
                if column_name not in existing_columns:
                    try:
                        sql = f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_type}'
                        print(f"🔧 Adding: {sql}")
                        cursor.execute(sql)
                        conn.commit()
                        print(f"✅ Added column: {table_name}.{column_name}")
                        total_columns_added += 1
                    except Exception as col_error:
                        print(f"❌ Error adding column {table_name}.{column_name}: {col_error}")
                        conn.rollback()
                        return False
                else:
                    print(f"✅ Column {table_name}.{column_name} already exists")
        
        # Verify all columns now exist
        print(f"\n🔍 Verification:")
        all_good = True
        
        for table_name, columns in table_fixes.items():
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s
            """, (table_name,))
            
            final_columns = [row[0] for row in cursor.fetchall()]
            required_columns = [col[0] for col in columns]
            missing = [col for col in required_columns if col not in final_columns]
            
            if missing:
                print(f"❌ {table_name} still missing: {missing}")
                all_good = False
            else:
                print(f"✅ {table_name} has all required columns")
        
        cursor.close()
        conn.close()
        
        if all_good:
            print(f"\n🎉 Complete database fix successful!")
            print(f"📊 Added {total_columns_added} columns total")
            print("🚀 All functionality should now work!")
            return True
        else:
            print(f"\n❌ Some columns are still missing")
            return False
            
    except Exception as e:
        print(f"❌ Complete database fix error: {e}")
        return False

if __name__ == "__main__":
    complete_database_fix()