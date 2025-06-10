"""
Add updated_at column to Farm table
Save as: add_updated_at_column.py
"""

import sqlite3
import os
import sys
from datetime import datetime

def add_updated_at_column():
    """Add updated_at column to Farm table"""
    try:
        # Look for SQLite database file
        db_files = ['instance/database.db', 'database.db', 'app.db', 'farm.db']
        db_path = None
        
        for file_path in db_files:
            if os.path.exists(file_path):
                db_path = file_path
                break
        
        if not db_path:
            print("❌ SQLite database file not found")
            return False
        
        print(f"📁 Found database: {db_path}")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if updated_at column already exists
        cursor.execute("PRAGMA table_info(farm)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'updated_at' in columns:
            print("✅ updated_at column already exists")
            conn.close()
            return True
        
        print("📝 Adding updated_at column...")
        
        # Add the updated_at column with current timestamp as default
        current_time = datetime.utcnow().isoformat()
        cursor.execute(f"""
            ALTER TABLE farm 
            ADD COLUMN updated_at DATETIME DEFAULT '{current_time}'
        """)
        
        # Update existing records to have the current timestamp
        cursor.execute(f"""
            UPDATE farm 
            SET updated_at = '{current_time}' 
            WHERE updated_at IS NULL
        """)
        
        conn.commit()
        print("✅ updated_at column added successfully")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(farm)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'updated_at' in columns:
            print("✅ Migration verification successful")
            conn.close()
            return True
        else:
            print("❌ Migration verification failed")
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Adding updated_at column to Farm table...")
    success = add_updated_at_column()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("You can now use updated_at in your Farm model")
    else:
        print("\n❌ Migration failed")
        print("Consider removing updated_at from your Farm model instead")
    
    sys.exit(0 if success else 1)