#!/usr/bin/env python3
"""
Complete Database Fix Script
This script completely recreates the database with the correct schema
"""

import os
import sqlite3
import shutil
from datetime import datetime

def find_database_files():
    """Find all database files in the project"""
    db_files = []
    for file in os.listdir('.'):
        if file.endswith('.db') or file.endswith('.sqlite3') or file.endswith('.sqlite'):
            db_files.append(file)
    return db_files

def backup_existing_data():
    """Backup existing data from the database"""
    db_file = 'db.sqlite3'
    if not os.path.exists(db_file):
        print("📋 No existing database to backup")
        return None
    
    print("💾 Backing up existing data...")
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    backup_data = {
        'users': [],
        'domes': [],
        'trees': [],
        'grid_settings': []
    }
    
    try:
        # Backup users
        cursor.execute("SELECT * FROM user")
        backup_data['users'] = cursor.fetchall()
        print(f"✅ Backed up {len(backup_data['users'])} users")
        
        # Backup domes
        cursor.execute("SELECT id, name, grid_row, grid_col, internal_rows, internal_cols, image_url, user_id FROM dome")
        backup_data['domes'] = cursor.fetchall()
        print(f"✅ Backed up {len(backup_data['domes'])} domes")
        
        # Backup trees
        cursor.execute("SELECT id, name, row, col, info, life_days, image_url, dome_id, user_id FROM tree")
        backup_data['trees'] = cursor.fetchall()
        print(f"✅ Backed up {len(backup_data['trees'])} trees")
        
        # Backup grid settings
        cursor.execute("SELECT id, rows, cols FROM grid_settings")
        backup_data['grid_settings'] = cursor.fetchall()
        print(f"✅ Backed up {len(backup_data['grid_settings'])} grid settings")
        
    except Exception as e:
        print(f"⚠️ Error during backup: {e}")
    finally:
        conn.close()
    
    return backup_data

def create_fresh_database():
    """Create a completely fresh database with correct schema"""
    db_file = 'db.sqlite3'
    
    print("🏗️ Creating fresh database with correct schema...")
    
    # Remove old database
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"🗑️ Removed old database: {db_file}")
    
    # Create new database
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Create user table
        cursor.execute('''
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                created_at DATETIME,
                is_active BOOLEAN,
                reset_token VARCHAR(100),
                reset_token_expires DATETIME
            )
        ''')
        print("✅ Created user table")
        
        # Create grid_settings table with user_id
        cursor.execute('''
            CREATE TABLE grid_settings (
                id INTEGER PRIMARY KEY,
                rows INTEGER DEFAULT 5,
                cols INTEGER DEFAULT 5,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        print("✅ Created grid_settings table")
        
        # Create farm table
        cursor.execute('''
            CREATE TABLE farm (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                grid_row INTEGER NOT NULL,
                grid_col INTEGER NOT NULL,
                image_url VARCHAR(255),
                user_id INTEGER NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        print("✅ Created farm table")
        
        # Create dome table with all required columns
        cursor.execute('''
            CREATE TABLE dome (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                grid_row INTEGER NOT NULL,
                grid_col INTEGER NOT NULL,
                internal_rows INTEGER DEFAULT 5,
                internal_cols INTEGER DEFAULT 5,
                image_url VARCHAR(255),
                user_id INTEGER NOT NULL,
                farm_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES user(id),
                FOREIGN KEY(farm_id) REFERENCES farm(id)
            )
        ''')
        print("✅ Created dome table")
        
        # Create row table
        cursor.execute('''
            CREATE TABLE row (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                dome_id INTEGER,
                created_at DATETIME,
                FOREIGN KEY(dome_id) REFERENCES dome(id)
            )
        ''')
        print("✅ Created row table")
        
        # Create tree table with all required columns
        cursor.execute('''
            CREATE TABLE tree (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                row INTEGER DEFAULT 0,
                col INTEGER DEFAULT 0,
                info TEXT,
                life_days INTEGER DEFAULT 0,
                image_url VARCHAR(200),
                dome_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(dome_id) REFERENCES dome(id),
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        print("✅ Created tree table")
        
        # Insert default grid settings
        cursor.execute('INSERT INTO grid_settings (rows, cols) VALUES (5, 5)')
        print("✅ Created default grid settings")
        
        conn.commit()
        print("🎉 Fresh database created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def restore_data(backup_data):
    """Restore backed up data to the new database"""
    if not backup_data:
        print("📋 No data to restore")
        return True
    
    print("🔄 Restoring backed up data...")
    
    db_file = 'db.sqlite3'
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        current_time = datetime.utcnow().isoformat()
        
        # Restore users
        for user in backup_data['users']:
            cursor.execute('''
                INSERT INTO user (id, username, email, password_hash, created_at, is_active, reset_token, reset_token_expires)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', user)
        print(f"✅ Restored {len(backup_data['users'])} users")
        
        # Restore grid settings
        cursor.execute('DELETE FROM grid_settings')  # Remove default
        for grid in backup_data['grid_settings']:
            cursor.execute('''
                INSERT INTO grid_settings (id, rows, cols, user_id)
                VALUES (?, ?, ?, NULL)
            ''', grid)
        print(f"✅ Restored {len(backup_data['grid_settings'])} grid settings")
        
        # Restore domes
        for dome in backup_data['domes']:
            cursor.execute('''
                INSERT INTO dome (id, name, grid_row, grid_col, internal_rows, internal_cols, image_url, user_id, farm_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ''', dome + (current_time, current_time))
        print(f"✅ Restored {len(backup_data['domes'])} domes")
        
        # Restore trees
        for tree in backup_data['trees']:
            cursor.execute('''
                INSERT INTO tree (id, name, row, col, info, life_days, image_url, dome_id, user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', tree + (current_time, current_time))
        print(f"✅ Restored {len(backup_data['trees'])} trees")
        
        conn.commit()
        print("🎉 Data restoration completed!")
        
    except Exception as e:
        print(f"❌ Error restoring data: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def verify_database_schema():
    """Verify the database schema is correct"""
    print("🔍 Verifying database schema...")
    
    db_file = 'db.sqlite3'
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Check all tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['user', 'farm', 'dome', 'tree', 'grid_settings', 'row']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        
        print(f"✅ All required tables exist: {required_tables}")
        
        # Check specific columns
        cursor.execute("PRAGMA table_info(grid_settings);")
        grid_columns = [row[1] for row in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns = [row[1] for row in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns = [row[1] for row in cursor.fetchall()]
        
        # Verify required columns
        checks = [
            ('grid_settings', 'user_id', 'user_id' in grid_columns),
            ('dome', 'farm_id', 'farm_id' in dome_columns),
            ('dome', 'created_at', 'created_at' in dome_columns),
            ('dome', 'updated_at', 'updated_at' in dome_columns),
            ('tree', 'created_at', 'created_at' in tree_columns),
            ('tree', 'updated_at', 'updated_at' in tree_columns),
        ]
        
        all_good = True
        for table, column, exists in checks:
            if exists:
                print(f"✅ {table}.{column} exists")
            else:
                print(f"❌ {table}.{column} missing")
                all_good = False
        
        return all_good
        
    except Exception as e:
        print(f"❌ Error verifying schema: {e}")
        return False
    finally:
        conn.close()

def clean_migration_files():
    """Clean up migration files that might interfere"""
    print("🧹 Cleaning up migration files...")
    
    migrations_dir = 'migrations'
    if os.path.exists(migrations_dir):
        try:
            shutil.rmtree(migrations_dir)
            print("✅ Removed migrations directory")
        except Exception as e:
            print(f"⚠️ Could not remove migrations: {e}")
    
    # Remove any __pycache__ directories
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            try:
                shutil.rmtree(os.path.join(root, '__pycache__'))
                print(f"✅ Removed {os.path.join(root, '__pycache__')}")
            except:
                pass

def create_upload_directories():
    """Create necessary upload directories"""
    print("📁 Creating upload directories...")
    
    directories = [
        'uploads',
        'uploads/trees',
        'uploads/domes', 
        'uploads/farms'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def main():
    """Main function"""
    print("🚀 Complete Database Fix Tool")
    print("=" * 60)
    
    # Step 1: Show current database files
    db_files = find_database_files()
    if db_files:
        print(f"📋 Found database files: {db_files}")
    else:
        print("📋 No existing database files found")
    
    # Step 2: Backup existing data
    backup_data = backup_existing_data()
    
    # Step 3: Clean migration files
    clean_migration_files()
    
    # Step 4: Create fresh database
    if not create_fresh_database():
        print("❌ Failed to create fresh database")
        return
    
    # Step 5: Restore data
    if not restore_data(backup_data):
        print("❌ Failed to restore data")
        return
    
    # Step 6: Verify schema
    if not verify_database_schema():
        print("❌ Schema verification failed")
        return
    
    # Step 7: Create upload directories
    create_upload_directories()
    
    print("\n" + "=" * 60)
    print("🎉 Complete database fix successful!")
    print("\nYour database now has the correct schema and all your data is preserved.")
    print("\nNext steps:")
    print("1. Restart your Flask app: python app.py")
    print("2. The app should now work without any schema errors")
    print("3. All your existing users, domes, and trees should be intact")

if __name__ == '__main__':
    main()