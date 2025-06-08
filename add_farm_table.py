#!/usr/bin/env python3
"""
Add Farm Table to Existing Database
This script adds the farm table and farm_id column to the existing database
"""

import sqlite3
import os
from datetime import datetime

def add_farm_table():
    """Add farm table and update dome table"""
    db_file = 'db.sqlite3'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return False
    
    print("🏗️ Adding farm table to existing database...")
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Check if farm table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm';")
        if cursor.fetchone():
            print("✅ Farm table already exists")
        else:
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
        
        # Check if dome table has farm_id column
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns = [row[1] for row in cursor.fetchall()]
        
        if 'farm_id' not in dome_columns:
            print("➕ Adding farm_id column to dome table...")
            cursor.execute("ALTER TABLE dome ADD COLUMN farm_id INTEGER;")
            print("✅ Added farm_id column to dome table")
        else:
            print("✅ dome.farm_id already exists")
        
        # Check if dome table has created_at and updated_at columns
        if 'created_at' not in dome_columns:
            cursor.execute("ALTER TABLE dome ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at to dome table")
        
        if 'updated_at' not in dome_columns:
            cursor.execute("ALTER TABLE dome ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at to dome table")
        
        # Check if tree table has created_at and updated_at columns
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns = [row[1] for row in cursor.fetchall()]
        
        if 'created_at' not in tree_columns:
            cursor.execute("ALTER TABLE tree ADD COLUMN created_at DATETIME;")
            print("✅ Added created_at to tree table")
        
        if 'updated_at' not in tree_columns:
            cursor.execute("ALTER TABLE tree ADD COLUMN updated_at DATETIME;")
            print("✅ Added updated_at to tree table")
        
        # Update existing records with default timestamps
        current_time = datetime.utcnow().isoformat()
        
        # Update dome records
        cursor.execute("UPDATE dome SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_domes = cursor.rowcount
        if updated_domes > 0:
            print(f"✅ Updated {updated_domes} dome records with timestamps")
        
        # Update tree records
        cursor.execute("UPDATE tree SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        updated_trees = cursor.rowcount
        if updated_trees > 0:
            print(f"✅ Updated {updated_trees} tree records with timestamps")
        
        # Commit all changes
        conn.commit()
        print("🎉 Farm table and columns added successfully!")
        
        # Verify the changes
        print("\n🔍 Verifying changes...")
        
        # Check farm table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm';")
        if cursor.fetchone():
            print("✅ farm table exists")
        
        # Check dome columns
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns_after = [row[1] for row in cursor.fetchall()]
        
        required_dome_columns = ['farm_id', 'created_at', 'updated_at']
        for col in required_dome_columns:
            if col in dome_columns_after:
                print(f"✅ dome.{col} exists")
            else:
                print(f"❌ dome.{col} missing")
        
        # Check tree columns
        cursor.execute("PRAGMA table_info(tree);")
        tree_columns_after = [row[1] for row in cursor.fetchall()]
        
        required_tree_columns = ['created_at', 'updated_at']
        for col in required_tree_columns:
            if col in tree_columns_after:
                print(f"✅ tree.{col} exists")
            else:
                print(f"❌ tree.{col} missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding farm table: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def create_upload_directories():
    """Create farm upload directory"""
    print("\n📁 Creating farm upload directory...")
    
    farm_dir = os.path.join('uploads', 'farms')
    os.makedirs(farm_dir, exist_ok=True)
    print(f"✅ Created directory: {farm_dir}")

def show_database_info():
    """Show current database structure"""
    db_file = 'db.sqlite3'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return
    
    print("\n📋 Current database structure:")
    print("=" * 50)
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            print(f"\n📊 Table: {table}")
            cursor.execute(f"PRAGMA table_info({table});")
            columns = cursor.fetchall()
            
            for col in columns:
                col_id, name, data_type, not_null, default, pk = col
                pk_str = " (PRIMARY KEY)" if pk else ""
                not_null_str = " NOT NULL" if not_null else ""
                default_str = f" DEFAULT {default}" if default else ""
                print(f"  - {name}: {data_type}{not_null_str}{default_str}{pk_str}")
        
        # Show record counts
        print(f"\n📈 Record counts:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  - {table}: {count} records")
            
    except Exception as e:
        print(f"❌ Error showing database info: {e}")
    finally:
        conn.close()

def main():
    """Main function"""
    print("🚜 Farm Table Addition Script")
    print("=" * 50)
    
    # Show current database structure
    show_database_info()
    
    # Add farm table and columns
    if add_farm_table():
        # Create upload directories
        create_upload_directories()
        
        print("\n" + "=" * 50)
        print("🎉 Database update completed successfully!")
        print("\nChanges made:")
        print("✅ Added farm table")
        print("✅ Added farm_id column to dome table")
        print("✅ Added created_at/updated_at columns to dome and tree tables")
        print("✅ Created uploads/farms directory")
        print("\nNext steps:")
        print("1. Update your models.py file")
        print("2. Add farm routes to app.py")
        print("3. Create farm.html template")
        print("4. Restart your Flask app: python app.py")
        print("=" * 50)
    else:
        print("\n❌ Database update failed!")
        print("Please check the errors above and try again.")

if __name__ == '__main__':
    main()