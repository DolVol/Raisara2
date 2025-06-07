import sqlite3
import os

def check_database(db_path):
    """Check if database exists and has user data"""
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check users
        cursor.execute("SELECT COUNT(*) FROM user")
        user_count = cursor.fetchone()[0]
        
        # Check domes
        cursor.execute("SELECT COUNT(*) FROM dome")
        dome_count = cursor.fetchone()[0]
        
        # Check trees
        cursor.execute("SELECT COUNT(*) FROM tree")
        tree_count = cursor.fetchone()[0]
        
        print(f"✅ Database: {db_path}")
        print(f"   Users: {user_count}")
        print(f"   Domes: {dome_count}")
        print(f"   Trees: {tree_count}")
        
        if user_count > 0:
            cursor.execute("SELECT id, username, email FROM user")
            users = cursor.fetchall()
            print(f"   User details:")
            for user in users:
                print(f"     - ID: {user[0]}, Username: {user[1]}, Email: {user[2]}")
        
        conn.close()
        return user_count > 0
        
    except Exception as e:
        print(f"❌ Error checking {db_path}: {e}")
        return False

def main():
    print("🔍 Searching for database files with user data...\n")
    
    # Check possible database locations
    db_paths = [
        'db.sqlite3',
        'instance/db.sqlite3',
        'instance\\db.sqlite3',
        'app.db',
        'instance/app.db'
    ]
    
    found_data = False
    
    for db_path in db_paths:
        if check_database(db_path):
            found_data = True
            print(f"🎯 FOUND USER DATA IN: {db_path}\n")
        else:
            print()
    
    if not found_data:
        print("❌ No user data found in any database files!")
        print("Your data might be in a different location or lost.")
    else:
        print("✅ User data located! Update your app.py to use the correct database path.")

if __name__ == '__main__':
    main()