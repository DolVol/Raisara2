"""
Database Migration Script
Run this script to add user_id columns to existing tables and migrate data
"""

import sqlite3
import os

def migrate_database():
    """Add user_id columns to dome and tree tables"""
    
    # Connect to the database
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        print("🔄 Starting database migration...")
        
        # Check if user_id column exists in dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in dome_columns:
            print("➕ Adding user_id column to dome table...")
            cursor.execute('ALTER TABLE dome ADD COLUMN user_id INTEGER')
            
            # Get the first user ID (or create a default user)
            cursor.execute('SELECT id FROM user LIMIT 1')
            user_result = cursor.fetchone()
            
            if user_result:
                first_user_id = user_result[0]
                print(f"👤 Assigning existing domes to user ID: {first_user_id}")
                
                # Update all existing domes to belong to the first user
                cursor.execute('UPDATE dome SET user_id = ? WHERE user_id IS NULL', (first_user_id,))
                print(f"✅ Updated {cursor.rowcount} domes")
            else:
                print("⚠️ No users found in database. Please create a user first.")
        else:
            print("✅ user_id column already exists in dome table")
        
        # Check if user_id column exists in tree table
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in tree_columns:
            print("➕ Adding user_id column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN user_id INTEGER')
            
            # Get the first user ID
            cursor.execute('SELECT id FROM user LIMIT 1')
            user_result = cursor.fetchone()
            
            if user_result:
                first_user_id = user_result[0]
                print(f"👤 Assigning existing trees to user ID: {first_user_id}")
                
                # Update all existing trees to belong to the first user
                cursor.execute('UPDATE tree SET user_id = ? WHERE user_id IS NULL', (first_user_id,))
                print(f"✅ Updated {cursor.rowcount} trees")
        else:
            print("✅ user_id column already exists in tree table")
        
        # Add other missing columns while we're at it
        if 'image_url' not in dome_columns:
            print("➕ Adding image_url column to dome table...")
            cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
        
        if 'image_url' not in tree_columns:
            print("➕ Adding image_url column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
        
        if 'info' not in tree_columns:
            print("➕ Adding info column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
        
        if 'life_days' not in tree_columns:
            print("➕ Adding life_days column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
        
        # Commit all changes
        conn.commit()
        print("✅ Database migration completed successfully!")
        
        # Show summary
        cursor.execute('SELECT COUNT(*) FROM dome WHERE user_id IS NOT NULL')
        dome_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tree WHERE user_id IS NOT NULL')
        tree_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM user')
        user_count = cursor.fetchone()[0]
        
        print(f"\n📊 Migration Summary:")
        print(f"   Users: {user_count}")
        print(f"   Domes with user_id: {dome_count}")
        print(f"   Trees with user_id: {tree_count}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        print("Please run your Flask app first to create the database.")
        exit(1)
    
    migrate_database()
    print("\n🎉 Migration complete! You can now restart your Flask app.")