"""
Flask-based Render Migration Script
This script uses your Flask app's database connection to add missing columns
Can be run on Render server
"""

import os
import sys
from datetime import datetime

def run_render_migration():
    """Run migration using Flask app context"""
    try:
        # Import Flask app and database
        from app import app, db
        from sqlalchemy import text
        
        print("🚀 Flask-based Render Migration Tool")
        print("=" * 45)
        
        with app.app_context():
            print("🔗 Connected to database via Flask app")
            
            # Detect database type
            database_url = os.environ.get('DATABASE_URL', '')
            if 'postgresql' in database_url or 'postgres' in database_url:
                db_type = "PostgreSQL"
                print("🐘 Detected PostgreSQL database (Render)")
            else:
                db_type = "SQLite"
                print("🗄️ Detected SQLite database (Local)")
            
            # Check current farm table structure
            print("🔍 Checking farm table structure...")
            
            try:
                if db_type == "PostgreSQL":
                    # PostgreSQL approach
                    result = db.session.execute(text("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns 
                        WHERE table_name = 'farm'
                        ORDER BY ordinal_position
                    """))
                    columns = result.fetchall()
                    column_names = [col[0] for col in columns]
                    
                else:
                    # SQLite approach
                    result = db.session.execute(text("PRAGMA table_info(farm)"))
                    sqlite_columns = result.fetchall()
                    columns = [(col[1], col[2], "YES" if not col[3] else "NO", col[4]) for col in sqlite_columns]
                    column_names = [col[1] for col in sqlite_columns]
                
                if not columns:
                    print("❌ Farm table not found!")
                    return False
                
                print(f"\n📋 Current farm table columns ({db_type}):")
                print("-" * 60)
                for col in columns:
                    nullable = "NULL" if col[2] == "YES" else "NOT NULL"
                    default = f"DEFAULT {col[3]}" if col[3] else ""
                    print(f"  {col[0]:<20} {col[1]:<15} {nullable:<10} {default}")
                
                # Check for missing columns
                missing_columns = []
                required_columns = ['password_hash', 'updated_at']
                
                for col_name in required_columns:
                    if col_name not in column_names:
                        missing_columns.append(col_name)
                
                if not missing_columns:
                    print("\n✅ All required columns already exist!")
                    return True
                
                print(f"\n⚠️ Missing columns: {missing_columns}")
                
                # Add missing columns based on database type
                for col_name in missing_columns:
                    print(f"📝 Adding column: {col_name}")
                    
                    try:
                        if col_name == 'password_hash':
                            if db_type == "PostgreSQL":
                                db.session.execute(text("""
                                    ALTER TABLE farm 
                                    ADD COLUMN password_hash VARCHAR(255)
                                """))
                            else:  # SQLite
                                db.session.execute(text("""
                                    ALTER TABLE farm 
                                    ADD COLUMN password_hash TEXT
                                """))
                            print(f"✅ Added {col_name} column")
                            
                        elif col_name == 'updated_at':
                            if db_type == "PostgreSQL":
                                db.session.execute(text("""
                                    ALTER TABLE farm 
                                    ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                """))
                            else:  # SQLite
                                db.session.execute(text("""
                                    ALTER TABLE farm 
                                    ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                                """))
                            
                            # Update existing records
                            db.session.execute(text("""
                                UPDATE farm 
                                SET updated_at = CURRENT_TIMESTAMP 
                                WHERE updated_at IS NULL
                            """))
                            print(f"✅ Added {col_name} column and updated existing records")
                            
                    except Exception as add_error:
                        if "already exists" in str(add_error).lower() or "duplicate column" in str(add_error).lower():
                            print(f"⚠️ Column {col_name} already exists")
                        else:
                            print(f"❌ Failed to add {col_name}: {str(add_error)}")
                            db.session.rollback()
                            return False
                
                # Commit changes
                db.session.commit()
                print("✅ All columns added successfully")
                
                # Verify migration
                print("🔍 Verifying migration...")
                
                result = db.session.execute(text("""
                    SELECT id, name, password_hash, updated_at 
                    FROM farm 
                    LIMIT 1
                """))
                
                test_record = result.fetchone()
                print("✅ Migration verification successful")
                
                if test_record:
                    print(f"Sample record: ID={test_record[0]}, Name={test_record[1]}, HasPassword={bool(test_record[2])}")
                else:
                    print("✅ No existing records, but columns are accessible")
                
                print(f"\n🎉 {db_type} migration completed successfully!")
                return True
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Migration error: {str(e)}")
                return False
                
    except Exception as e:
        print(f"❌ Failed to run migration: {str(e)}")
        return False

def check_environment():
    """Check environment and provide guidance"""
    print("🔧 Environment Check:")
    print(f"  Python version: {sys.version.split()[0]}")
    print(f"  Current directory: {os.getcwd()}")
    print(f"  app.py exists: {os.path.exists('app.py')}")
    
    # Check database URL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if 'postgresql' in database_url or 'postgres' in database_url:
            print(f"  DATABASE_URL: PostgreSQL (Render)")
            print(f"  URL: {database_url[:50]}...")
        else:
            print(f"  DATABASE_URL: {database_url}")
    else:
        print("  DATABASE_URL: Not set (using local SQLite)")
    
    print()

def main():
    """Main function"""
    print("🌐 Universal Farm Migration Tool")
    print("=" * 40)
    print("This script works on both Render (PostgreSQL) and Local (SQLite)")
    print()
    
    check_environment()
    
    success = run_render_migration()
    
    if success:
        print("\n✅ Farm password migration completed!")
        print("\nWhat was added:")
        print("  🔒 password_hash column - for farm password protection")
        print("  📅 updated_at column - for tracking farm modifications")
        print("\nNext steps:")
        print("1. Restart your application (automatic on Render)")
        print("2. Test farm creation with password")
        print("3. Test farm access with password protection")
        print("4. Update your Farm model to include password methods")
    else:
        print("\n❌ Migration failed")
        print("\nTroubleshooting:")
        print("1. Check database connection")
        print("2. Verify farm table exists")
        print("3. Check database permissions")
        print("4. Review error messages above")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)