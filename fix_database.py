import sqlite3
import os
from sqlalchemy import create_engine, text, inspect

def fix_database():
    """Fix database schema issues"""
    db_path = 'db.sqlite3'
    
    print("🔧 Fixing database schema issues...")
    print(f"📁 Working with database: {os.path.abspath(db_path)}")
    
    # Step 1: Direct SQLite check
    print("\n🔍 Step 1: Direct SQLite inspection")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check dome table structure
        cursor.execute("PRAGMA table_info(dome);")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ Current dome columns: {columns}")
        
        # Check if farm_id exists
        has_farm_id = 'farm_id' in columns
        print(f"📊 Has farm_id: {has_farm_id}")
        
        if not has_farm_id:
            print("➕ Adding farm_id column...")
            cursor.execute("ALTER TABLE dome ADD COLUMN farm_id INTEGER;")
            conn.commit()
            print("✅ farm_id column added")
        
        # Check if created_at exists
        has_created_at = 'created_at' in columns
        if not has_created_at:
            print("➕ Adding created_at column...")
            cursor.execute("ALTER TABLE dome ADD COLUMN created_at DATETIME;")
            conn.commit()
            print("✅ created_at column added")
        
        # Check if updated_at exists
        has_updated_at = 'updated_at' in columns
        if not has_updated_at:
            print("➕ Adding updated_at column...")
            cursor.execute("ALTER TABLE dome ADD COLUMN updated_at DATETIME;")
            conn.commit()
            print("✅ updated_at column added")
        
        # Final check
        cursor.execute("PRAGMA table_info(dome);")
        final_columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ Final dome columns: {final_columns}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ SQLite error: {e}")
        return False
    
    # Step 2: SQLAlchemy check
    print("\n🔍 Step 2: SQLAlchemy inspection")
    try:
        engine = create_engine(f'sqlite:///{db_path}')
        inspector = inspect(engine)
        
        # Get columns via SQLAlchemy
        sqlalchemy_columns = [col['name'] for col in inspector.get_columns('dome')]
        print(f"✅ SQLAlchemy sees columns: {sqlalchemy_columns}")
        
        # Test query
        with engine.connect() as conn:
            result = conn.execute(text("SELECT farm_id FROM dome LIMIT 1;"))
            print("✅ SQLAlchemy can query farm_id column")
        
    except Exception as e:
        print(f"⚠️ SQLAlchemy error: {e}")
        print("🔄 This might be due to metadata caching")
    
    # Step 3: Force metadata refresh
    print("\n🔍 Step 3: Force metadata refresh")
    try:
        # Delete any cached metadata files
        cache_files = [
            'instance/db.sqlite3',
            'app.db',
            'database.db'
        ]
        
        for cache_file in cache_files:
            if os.path.exists(cache_file):
                print(f"🗑️ Removing cache file: {cache_file}")
                os.remove(cache_file)
        
        print("✅ Cache cleanup completed")
        
    except Exception as e:
        print(f"⚠️ Cache cleanup error: {e}")
    
    print("\n✅ Database fix completed!")
    print("\n🚀 Next steps:")
    print("1. Restart your Flask app: python app.py")
    print("2. The farm_info page should now work")
    
    return True

if __name__ == "__main__":
    fix_database()