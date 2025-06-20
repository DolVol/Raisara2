# add_farm_password_columns.py
import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

def get_database_url():
    """Get database URL from environment"""
    if os.getenv('RENDER'):
        database_url = os.getenv('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url or 'sqlite:///db.sqlite3'
    else:
        return 'sqlite:///db.sqlite3'

def is_postgresql(database_url):
    """Check if database is PostgreSQL"""
    return 'postgresql' in database_url

def column_exists(engine, table_name, column_name):
    """Check if column exists in table"""
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        return column_name in [col['name'] for col in columns]
    except Exception as e:
        print(f"Error checking column {column_name}: {e}")
        return False

def add_farm_password_columns():
    """Add password-related columns to farm table"""
    database_url = get_database_url()
    is_postgres = is_postgresql(database_url)
    
    print(f"🔧 Adding farm password columns...")
    print(f"Database: {'PostgreSQL' if is_postgres else 'SQLite'}")
    print(f"URL: {database_url[:50]}...")
    
    try:
        engine = create_engine(database_url)
        
        # Test connection
        with engine.connect() as conn:
            if is_postgres:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                print(f"✅ Connected to PostgreSQL: {version[:50]}...")
            else:
                result = conn.execute(text("SELECT sqlite_version()"))
                version = result.fetchone()[0]
                print(f"✅ Connected to SQLite: {version}")
        
        # Check if farm table exists
        inspector = inspect(engine)
        if 'farm' not in inspector.get_table_names():
            print("❌ Farm table does not exist!")
            return False
        
        # Columns to add
        columns_to_add = [
            ('password_hash', 'VARCHAR(200)'),
            ('reset_token', 'VARCHAR(100)'),
            ('reset_token_expires', 'TIMESTAMP')
        ]
        
        added_columns = []
        skipped_columns = []
        
        with engine.connect() as conn:
            for column_name, column_type in columns_to_add:
                if column_exists(engine, 'farm', column_name):
                    print(f"ℹ️ Column '{column_name}' already exists - skipping")
                    skipped_columns.append(column_name)
                else:
                    try:
                        # Add column
                        sql = f"ALTER TABLE farm ADD COLUMN {column_name} {column_type}"
                        conn.execute(text(sql))
                        conn.commit()
                        print(f"✅ Added column: {column_name} {column_type}")
                        added_columns.append(column_name)
                    except Exception as e:
                        print(f"❌ Failed to add column {column_name}: {e}")
                        return False
        
        # Summary
        print(f"\n📊 Migration Summary:")
        print(f"✅ Added columns: {len(added_columns)}")
        if added_columns:
            for col in added_columns:
                print(f"   - {col}")
        
        print(f"ℹ️ Skipped columns: {len(skipped_columns)}")
        if skipped_columns:
            for col in skipped_columns:
                print(f"   - {col}")
        
        print(f"\n🎉 Farm password columns migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def verify_columns():
    """Verify that columns were added successfully"""
    database_url = get_database_url()
    
    try:
        engine = create_engine(database_url)
        inspector = inspect(engine)
        columns = inspector.get_columns('farm')
        
        print(f"\n🔍 Verifying farm table columns:")
        required_columns = ['password_hash', 'reset_token', 'reset_token_expires']
        
        for col in columns:
            if col['name'] in required_columns:
                print(f"✅ {col['name']}: {col['type']}")
        
        # Check if all required columns exist
        existing_columns = [col['name'] for col in columns]
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        if missing_columns:
            print(f"❌ Missing columns: {missing_columns}")
            return False
        else:
            print(f"✅ All password columns are present!")
            return True
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == '__main__':
    print("🚀 Starting farm password columns migration...")
    
    # Add columns
    if add_farm_password_columns():
        # Verify columns
        if verify_columns():
            print("\n🎉 Migration completed successfully!")
            print("You can now use farm password functionality.")
        else:
            print("\n⚠️ Migration completed but verification failed.")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)