"""
Farm Password Migration Script
Save this as: migrate_farm_columns_enhanced.py
"""

import os
import sys
from datetime import datetime

def run_migration():
    """Run the migration using Flask-SQLAlchemy"""
    try:
        # Import Flask app and database
        from app import app, db
        from sqlalchemy import text
        
        print("🚀 Farm Password Migration Tool")
        print("=" * 40)
        
        with app.app_context():
            print("🔗 Connected to database successfully")
            
            # Check current farm table structure
            print("🔍 Checking farm table structure...")
            
            try:
                # Try SQLite approach (since you're using SQLite)
                result = db.session.execute(text("PRAGMA table_info(farm)"))
                columns = result.fetchall()
                
                if not columns:
                    print("❌ Farm table not found!")
                    return False
                
                print("\n📋 Current farm table columns:")
                print("-" * 50)
                column_names = []
                for col in columns:
                    column_names.append(col[1])
                    nullable = "NOT NULL" if col[3] else "NULL"
                    default = f"DEFAULT {col[4]}" if col[4] else ""
                    print(f"  {col[1]:<20} {col[2]:<15} {nullable:<10} {default}")
                
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
                
                # Add missing columns
                for col_name in missing_columns:
                    print(f"📝 Adding column: {col_name}")
                    
                    try:
                        if col_name == 'password_hash':
                            db.session.execute(text("ALTER TABLE farm ADD COLUMN password_hash TEXT"))
                            print(f"✅ Added {col_name} column")
                            
                        elif col_name == 'updated_at':
                            db.session.execute(text("ALTER TABLE farm ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                            
                            # Update existing records
                            db.session.execute(text("""
                                UPDATE farm 
                                SET updated_at = CURRENT_TIMESTAMP 
                                WHERE updated_at IS NULL
                            """))
                            print(f"✅ Added {col_name} column and updated existing records")
                            
                    except Exception as add_error:
                        if "duplicate column name" in str(add_error):
                            print(f"⚠️ Column {col_name} already exists")
                        else:
                            print(f"❌ Failed to add {col_name}: {str(add_error)}")
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
                
                print("\n🎉 Migration completed successfully!")
                return True
                
            except Exception as e:
                print(f"❌ Migration error: {str(e)}")
                return False
                
    except Exception as e:
        print(f"❌ Failed to run migration: {str(e)}")
        return False

def main():
    """Main function"""
    print("🔧 Environment Check:")
    print(f"  Python version: {sys.version.split()[0]}")
    print(f"  Current directory: {os.getcwd()}")
    print(f"  app.py exists: {os.path.exists('app.py')}")
    print()
    
    success = run_migration()
    
    if success:
        print("\n✅ Farm password migration completed!")
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. Test farm creation with password")
        print("3. Test farm access with password protection")
    else:
        print("\n❌ Migration failed")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)