# Create a file called create_db.py
import sqlite3
import os

def create_database():
    """Create empty database file"""
    db_path = 'db.sqlite3'
    
    try:
        # Create the database file
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create a simple table to initialize the database
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS temp_table (
                id INTEGER PRIMARY KEY
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Database file created: {db_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Creating database file...")
    if create_database():
        print("✅ Database created successfully")
        print("🚀 You can now run the migration script")
    else:
        print("❌ Failed to create database")