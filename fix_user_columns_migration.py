#!/usr/bin/env python3
"""
Fix User Table Columns Migration Script
This script adds the missing columns to the user table that are causing the login/registration errors.
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, MetaData, inspect
from datetime import datetime

# Load environment variables
load_dotenv()

def get_database_url():
    """Get database URL based on environment"""
    if os.getenv('RENDER'):
        # Use PostgreSQL on Render
        database_url = os.getenv('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            # Fix for SQLAlchemy 1.4+ compatibility
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    else:
        # Use SQLite for local development
        return 'sqlite:///db.sqlite3'

def is_postgresql(database_url):
    """Check if we're using PostgreSQL"""
    return 'postgresql' in database_url or 'postgres' in database_url

def check_and_add_user_columns():
    """Check and add missing columns to the user table"""
    database_url = get_database_url()
    
    if not database_url:
        print("❌ No database URL found")
        return False
    
    print(f"🔗 Connecting to database: {database_url[:50]}...")
    
    try:
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Check if user table exists
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if 'user' not in tables:
                print("❌ User table does not exist")
                return False
            
            print("✅ User table found")
            
            # Get current columns
            columns = inspector.get_columns('user')
            column_names = [col['name'] for col in columns]
            
            print(f"📋 Current user table columns: {column_names}")
            
            # Define missing columns that need to be added
            missing_columns = []
            
            if 'last_login' not in column_names:
                missing_columns.append('last_login')
            
            if 'previous_login' not in column_names:
                missing_columns.append('previous_login')
            
            if 'login_count' not in column_names:
                missing_columns.append('login_count')
            
            if not missing_columns:
                print("✅ All required columns already exist")
                return True
            
            print(f"🔧 Missing columns to add: {missing_columns}")
            
            # Add missing columns
            for column in missing_columns:
                try:
                    if is_postgresql(database_url):
                        # PostgreSQL syntax
                        if column == 'login_count':
                            sql = f'ALTER TABLE "user" ADD COLUMN {column} INTEGER DEFAULT 0'
                        else:
                            sql = f'ALTER TABLE "user" ADD COLUMN {column} TIMESTAMP'
                    else:
                        # SQLite syntax
                        if column == 'login_count':
                            sql = f'ALTER TABLE user ADD COLUMN {column} INTEGER DEFAULT 0'
                        else:
                            sql = f'ALTER TABLE user ADD COLUMN {column} DATETIME'
                    
                    print(f"🔧 Adding column {column}: {sql}")
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"✅ Successfully added column: {column}")
                    
                except Exception as col_error:
                    print(f"❌ Error adding column {column}: {col_error}")
                    return False
            
            # Verify columns were added
            inspector = inspect(engine)
            updated_columns = inspector.get_columns('user')
            updated_column_names = [col['name'] for col in updated_columns]
            
            print(f"📋 Updated user table columns: {updated_column_names}")
            
            # Check if all required columns are now present
            all_present = all(col in updated_column_names for col in ['last_login', 'previous_login', 'login_count'])
            
            if all_present:
                print("✅ All required columns successfully added to user table")
                return True
            else:
                print("❌ Some columns are still missing")
                return False
                
    except Exception as e:
        print(f"❌ Database error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main function"""
    print("🚀 Starting User Table Column Fix")
    print("=" * 50)
    
    success = check_and_add_user_columns()
    
    print("=" * 50)
    if success:
        print("✅ User table column fix completed successfully!")
        print("🎉 You can now try logging in/registering again")
    else:
        print("❌ User table column fix failed")
        print("💡 You may need to run this script with proper database permissions")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)