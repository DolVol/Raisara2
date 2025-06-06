"""
Find and Migrate Database Script
This script will find your database and add the missing user_id columns
"""

import sqlite3
import os
import glob

def find_database_files():
    """Find all possible SQLite database files"""
    possible_files = []
    
    # Common database file patterns
    patterns = [
        '*.sqlite3',
        '*.sqlite',
        '*.db',
        'instance/*.sqlite3',
        'instance/*.sqlite',
        'instance/*.db'
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        possible_files.extend(files)
    
    # Remove duplicates
    return list(set(possible_files))

def check_database_content(db_path):
    """Check what tables exist in the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        # Check for our required tables
        has_user = 'user' in tables
        has_dome = 'dome' in tables
        has_tree = 'tree' in tables
        
        # Count records if tables exist
        user_count = 0
        dome_count = 0
        tree_count = 0
        
        if has_user:
            cursor.execute("SELECT COUNT(*) FROM user")
            user_count = cursor.fetchone()[0]
        
        if has_dome:
            cursor.execute("SELECT COUNT(*) FROM dome")
            dome_count = cursor.fetchone()[0]
        
        if has_tree:
            cursor.execute("SELECT COUNT(*) FROM tree")
            tree_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'tables': tables,
            'has_required_tables': has_user and has_dome and has_tree,
            'user_count': user_count,
            'dome_count': dome_count,
            'tree_count': tree_count
        }
    except Exception as e:
        return {'error': str(e)}

def migrate_database(db_path):
    """Add user_id columns to dome and tree tables"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print(f"🔄 Migrating database: {db_path}")
        
        # Check if user_id column exists in dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Dome columns: {dome_columns}")
        
        # Check if user_id column exists in tree table
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Tree columns: {tree_columns}")
        
        changes_made = False
        
        # Add user_id to dome table if missing
        if 'user_id' not in dome_columns:
            print("➕ Adding user_id column to dome table...")
            cursor.execute('ALTER TABLE dome ADD COLUMN user_id INTEGER')
            changes_made = True
            
            # Get the first user ID
            cursor.execute('SELECT id FROM user LIMIT 1')
            user_result = cursor.fetchone()
            
            if user_result:
                first_user_id = user_result[0]
                print(f"👤 Assigning existing domes to user ID: {first_user_id}")
                cursor.execute('UPDATE dome SET user_id = ? WHERE user_id IS NULL', (first_user_id,))
                print(f"✅ Updated {cursor.rowcount} domes")
            else:
                print("⚠️ No users found. Domes will need user_id assigned later.")
        else:
            print("✅ user_id column already exists in dome table")
        
        # Add user_id to tree table if missing
        if 'user_id' not in tree_columns:
            print("➕ Adding user_id column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN user_id INTEGER')
            changes_made = True
            
            # Get the first user ID
            cursor.execute('SELECT id FROM user LIMIT 1')
            user_result = cursor.fetchone()
            
            if user_result:
                first_user_id = user_result[0]
                print(f"👤 Assigning existing trees to user ID: {first_user_id}")
                cursor.execute('UPDATE tree SET user_id = ? WHERE user_id IS NULL', (first_user_id,))
                print(f"✅ Updated {cursor.rowcount} trees")
            else:
                print("⚠️ No users found. Trees will need user_id assigned later.")
        else:
            print("✅ user_id column already exists in tree table")
        
        # Add other missing columns
        if 'image_url' not in dome_columns:
            print("➕ Adding image_url column to dome table...")
            cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
            changes_made = True
        
        if 'image_url' not in tree_columns:
            print("➕ Adding image_url column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
            changes_made = True
        
        if 'info' not in tree_columns:
            print("➕ Adding info column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
            changes_made = True
        
        if 'life_days' not in tree_columns:
            print("➕ Adding life_days column to tree table...")
            cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
            changes_made = True
        
        if changes_made:
            conn.commit()
            print("✅ Database migration completed successfully!")
        else:
            print("✅ No migration needed - all columns already exist!")
        
        # Show final summary
        cursor.execute('SELECT COUNT(*) FROM user')
        user_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM dome')
        dome_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tree')
        tree_count = cursor.fetchone()[0]
        
        print(f"\n📊 Final Database Summary:")
        print(f"   Users: {user_count}")
        print(f"   Domes: {dome_count}")
        print(f"   Trees: {tree_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def main():
    print("🔍 Searching for SQLite database files...")
    
    # Find all possible database files
    db_files = find_database_files()
    
    if not db_files:
        print("❌ No SQLite database files found!")
        print("\n📝 To create the database:")
        print("1. Run: python app.py")
        print("2. Visit http://127.0.0.1:5000 and register a user")
        print("3. Stop the app and run this script again")
        return
    
    print(f"📁 Found {len(db_files)} database file(s):")
    
    # Check each database file
    valid_databases = []
    for db_file in db_files:
        print(f"\n🔍 Checking: {db_file}")
        info = check_database_content(db_file)
        
        if 'error' in info:
            print(f"   ❌ Error: {info['error']}")
            continue
        
        print(f"   📋 Tables: {info['tables']}")
        print(f"   👥 Users: {info['user_count']}")
        print(f"   🏠 Domes: {info['dome_count']}")
        print(f"   🌳 Trees: {info['tree_count']}")
        
        if info['has_required_tables']:
            valid_databases.append(db_file)
            print("   ✅ Valid Flask app database")
        else:
            print("   ⚠️ Missing required tables")
    
    if not valid_databases:
        print("\n❌ No valid Flask app databases found!")
        print("Please run your Flask app first to create the database.")
        return
    
    # Use the first valid database (or let user choose if multiple)
    if len(valid_databases) == 1:
        chosen_db = valid_databases[0]
        print(f"\n🎯 Using database: {chosen_db}")
    else:
        print(f"\n🤔 Found {len(valid_databases)} valid databases:")
        for i, db in enumerate(valid_databases):
            print(f"   {i+1}. {db}")
        
        try:
            choice = int(input("Enter the number of the database to migrate: ")) - 1
            chosen_db = valid_databases[choice]
        except (ValueError, IndexError):
            chosen_db = valid_databases[0]
            print(f"Using first database: {chosen_db}")
    
    # Perform migration
    if migrate_database(chosen_db):
        print(f"\n🎉 Migration complete for: {chosen_db}")
        print("You can now restart your Flask app with user-specific data!")
    else:
        print(f"\n❌ Migration failed for: {chosen_db}")

if __name__ == '__main__':
    main()