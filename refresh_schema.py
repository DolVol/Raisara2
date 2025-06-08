#!/usr/bin/env python3
"""
SQLAlchemy Schema Refresh Script
This script forces SQLAlchemy to refresh its metadata cache
"""

import os
import sqlite3
from sqlalchemy import create_engine, MetaData, inspect

def refresh_sqlalchemy_schema():
    """Force SQLAlchemy to refresh its schema cache"""
    
    print("🔄 Refreshing SQLAlchemy schema cache...")
    
    # Database file path
    db_file = 'db.sqlite3'
    database_url = f'sqlite:///{db_file}'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        # Clear metadata cache
        metadata = MetaData()
        metadata.bind = engine
        
        # Force reflection of all tables
        print("🔍 Reflecting database schema...")
        metadata.reflect(bind=engine)
        
        # Check dome table specifically
        if 'dome' in metadata.tables:
            dome_table = metadata.tables['dome']
            columns = [col.name for col in dome_table.columns]
            print(f"✅ Dome table columns: {columns}")
            
            if 'farm_id' in columns:
                print("✅ farm_id column found in schema")
            else:
                print("❌ farm_id column NOT found in schema")
                return False
        
        # Use inspector to double-check
        inspector = inspect(engine)
        dome_columns = inspector.get_columns('dome')
        column_names = [col['name'] for col in dome_columns]
        print(f"🔍 Inspector found columns: {column_names}")
        
        if 'farm_id' in column_names:
            print("✅ Schema refresh successful!")
            return True
        else:
            print("❌ Schema refresh failed - farm_id still missing")
            return False
            
    except Exception as e:
        print(f"❌ Error refreshing schema: {e}")
        return False

def verify_database_directly():
    """Verify database structure directly with sqlite3"""
    print("\n🔍 Direct database verification...")
    
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        # Check dome table structure
        cursor.execute("PRAGMA table_info(dome);")
        columns = cursor.fetchall()
        
        print("📋 Dome table structure:")
        for col in columns:
            col_id, name, data_type, not_null, default, pk = col
            print(f"  - {name}: {data_type}")
        
        column_names = [col[1] for col in columns]
        
        if 'farm_id' in column_names:
            print("✅ farm_id column exists in database")
            return True
        else:
            print("❌ farm_id column missing from database")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False
    finally:
        conn.close()

def main():
    """Main function"""
    print("🔄 SQLAlchemy Schema Refresh Tool")
    print("=" * 50)
    
    # First verify database directly
    if not verify_database_directly():
        print("\n❌ Database verification failed!")
        print("Please run the database update script first:")
        print("python add_farm_columns.py")
        return
    
    # Refresh SQLAlchemy schema
    if refresh_sqlalchemy_schema():
        print("\n" + "=" * 50)
        print("🎉 Schema refresh completed successfully!")
        print("\nNext steps:")
        print("1. Start your Flask app: python app.py")
        print("2. Test farm_info page")
        print("=" * 50)
    else:
        print("\n❌ Schema refresh failed!")
        print("Try deleting any .pyc files and __pycache__ directories:")
        print("find . -name '*.pyc' -delete")
        print("find . -name '__pycache__' -type d -exec rm -rf {} +")

if __name__ == '__main__':
    main()