import sqlite3
import os

def migrate_database():
    """Add reset_token columns to existing user table"""
    
    db_path = 'db.sqlite3'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Checking current user table structure...")
        
        # Check current table structure
        cursor.execute("PRAGMA table_info(user)")
        columns = cursor.fetchall()
        
        print("Current columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check if reset_token columns already exist
        column_names = [col[1] for col in columns]
        
        if 'reset_token' not in column_names:
            print("\nAdding reset_token column...")
            cursor.execute("ALTER TABLE user ADD COLUMN reset_token VARCHAR(100)")
            print("✅ reset_token column added")
        else:
            print("✅ reset_token column already exists")
        
        if 'reset_token_expires' not in column_names:
            print("Adding reset_token_expires column...")
            cursor.execute("ALTER TABLE user ADD COLUMN reset_token_expires TIMESTAMP")
            print("✅ reset_token_expires column added")
        else:
            print("✅ reset_token_expires column already exists")
        
        # Commit changes
        conn.commit()
        
        # Verify the new structure
        print("\nUpdated table structure:")
        cursor.execute("PRAGMA table_info(user)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        print("\n🎉 Database migration completed successfully!")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Starting database migration...")
    success = migrate_database()
    
    if success:
        print("\n✅ Migration successful! You can now run your app:")
        print("   python app.py")
    else:
        print("\n❌ Migration failed. Please check the errors above.")