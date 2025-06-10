"""
Migration script to add password_hash column to Farm table
Run this script to update your database schema
"""

from sqlalchemy import text
from app import app, db
import sys

def add_farm_password_column():
    """Add password_hash column to Farm table"""
    try:
        with app.app_context():
            print("🔧 Checking if password_hash column exists...")
            
            # Check if column already exists (PostgreSQL)
            try:
                result = db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='farm' AND column_name='password_hash'
                """))
                
                if result.fetchone():
                    print("✅ password_hash column already exists")
                    return True
                    
            except Exception:
                # Might be SQLite, try different approach
                try:
                    result = db.session.execute(text("PRAGMA table_info(farm)"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'password_hash' in columns:
                        print("✅ password_hash column already exists")
                        return True
                except Exception:
                    pass
            
            print("📝 Adding password_hash column to farm table...")
            
            # Try PostgreSQL syntax first
            try:
                db.session.execute(text("""
                    ALTER TABLE farm 
                    ADD COLUMN password_hash VARCHAR(255)
                """))
                db.session.commit()
                print("✅ password_hash column added successfully (PostgreSQL)")
                return True
                
            except Exception as e:
                db.session.rollback()
                print(f"⚠️ PostgreSQL syntax failed: {str(e)}")
                
                # Try SQLite syntax
                try:
                    db.session.execute(text("""
                        ALTER TABLE farm 
                        ADD COLUMN password_hash TEXT
                    """))
                    db.session.commit()
                    print("✅ password_hash column added successfully (SQLite)")
                    return True
                    
                except Exception as e2:
                    db.session.rollback()
                    print(f"❌ SQLite syntax also failed: {str(e2)}")
                    return False
            
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        return False

def verify_migration():
    """Verify that the migration was successful"""
    try:
        with app.app_context():
            # Try to query the new column
            result = db.session.execute(text("SELECT password_hash FROM farm LIMIT 1"))
            print("✅ Migration verification successful - password_hash column is accessible")
            return True
    except Exception as e:
        print(f"❌ Migration verification failed: {str(e)}")
        return False

def main():
    """Main migration function"""
    print("🚀 Starting Farm Password Migration...")
    print("=" * 50)
    
    # Add the column
    if add_farm_password_column():
        print("\n🔍 Verifying migration...")
        if verify_migration():
            print("\n🎉 Migration completed successfully!")
            print("\nNext steps:")
            print("1. Restart your Flask application")
            print("2. Test farm creation with password")
            print("3. Test farm access with password protection")
            return True
        else:
            print("\n⚠️ Migration completed but verification failed")
            return False
    else:
        print("\n❌ Migration failed")
        print("\nTroubleshooting:")
        print("1. Check your database connection")
        print("2. Ensure you have proper database permissions")
        print("3. Check if the farm table exists")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)