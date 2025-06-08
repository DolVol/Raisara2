import sqlite3
import os
from datetime import datetime

def add_farm_support():
    """Add farm table and farm_id column to dome table"""
    db_path = 'db.sqlite3'
    
    if not os.path.exists(db_path):
        print("❌ Database file not found")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Current database structure:")
        
        # Check if user table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        user_exists = cursor.fetchone()
        if not user_exists:
            print("➕ Creating user table...")
            cursor.execute('''
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    password_hash VARCHAR(200) NOT NULL,
                    created_at DATETIME,
                    is_active BOOLEAN DEFAULT 1,
                    reset_token VARCHAR(100),
                    reset_token_expires DATETIME
                )
            ''')
            print("✅ Created user table")
        
        # Check if grid_settings table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grid_settings'")
        grid_exists = cursor.fetchone()
        if not grid_exists:
            print("➕ Creating grid_settings table...")
            cursor.execute('''
                CREATE TABLE grid_settings (
                    id INTEGER PRIMARY KEY,
                    rows INTEGER DEFAULT 5,
                    cols INTEGER DEFAULT 5
                )
            ''')
            # Insert default grid settings
            cursor.execute("INSERT INTO grid_settings (rows, cols) VALUES (5, 5)")
            print("✅ Created grid_settings table")
        
        # Check if dome table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dome'")
        dome_exists = cursor.fetchone()
        if not dome_exists:
            print("➕ Creating dome table...")
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
            print("✅ Created dome table with farm_id column")
        else:
            # Check current dome table structure
            cursor.execute("PRAGMA table_info(dome)")
            dome_columns = [column[1] for column in cursor.fetchall()]
            print(f"Dome columns: {dome_columns}")
            
            # Add farm_id column if it doesn't exist
            if 'farm_id' not in dome_columns:
                print("➕ Adding farm_id column to dome table...")
                cursor.execute("ALTER TABLE dome ADD COLUMN farm_id INTEGER")
                print("✅ Added farm_id column to dome table")
            else:
                print("✅ farm_id column already exists")
            
            # Add created_at and updated_at columns if they don't exist
            if 'created_at' not in dome_columns:
                print("➕ Adding created_at column to dome table...")
                cursor.execute("ALTER TABLE dome ADD COLUMN created_at DATETIME")
                print("✅ Added created_at column")
            
            if 'updated_at' not in dome_columns:
                print("➕ Adding updated_at column to dome table...")
                cursor.execute("ALTER TABLE dome ADD COLUMN updated_at DATETIME")
                print("✅ Added updated_at column")
        
        # Check if tree table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tree'")
        tree_exists = cursor.fetchone()
        if not tree_exists:
            print("➕ Creating tree table...")
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
        else:
            # Check tree table and add timestamps if needed
            cursor.execute("PRAGMA table_info(tree)")
            tree_columns = [column[1] for column in cursor.fetchall()]
            
            if 'created_at' not in tree_columns:
                cursor.execute("ALTER TABLE tree ADD COLUMN created_at DATETIME")
                print("✅ Added created_at to tree table")
            
            if 'updated_at' not in tree_columns:
                cursor.execute("ALTER TABLE tree ADD COLUMN updated_at DATETIME")
                print("✅ Added updated_at to tree table")
        
        # Check if farm table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm'")
        farm_exists = cursor.fetchone()
        if not farm_exists:
            print("➕ Creating farm table...")
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
        
        # Update existing records with timestamps
        current_time = datetime.utcnow().isoformat()
        
        # Update dome records
        cursor.execute("UPDATE dome SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        dome_updated_count = cursor.rowcount
        if dome_updated_count > 0:
            print(f"✅ Updated {dome_updated_count} dome records with timestamps")
        
        # Update tree records
        cursor.execute("UPDATE tree SET created_at = ?, updated_at = ? WHERE created_at IS NULL", 
                      (current_time, current_time))
        tree_updated_count = cursor.rowcount
        if tree_updated_count > 0:
            print(f"✅ Updated {tree_updated_count} tree records with timestamps")
        
        conn.commit()
        
        # Verify the changes
        print("\n🔍 Verifying final database structure:")
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall()]
        print(f"Tables: {tables}")
        
        # Check dome table structure
        cursor.execute("PRAGMA table_info(dome)")
        final_dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Dome columns: {final_dome_columns}")
        
        if 'farm_id' in final_dome_columns:
            print("✅ farm_id column successfully added")
        else:
            print("❌ farm_id column still missing")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("🔧 Creating complete database structure with farm support...")
    if add_farm_support():
        print("\n✅ Database setup completed successfully")
        print("🚀 You can now start your Flask app")
        print("\nNext steps:")
        print("1. Start your Flask app: python app.py")
        print("2. Go to http://192.168.1.38:5000/register")
        print("3. Create a user account")
        print("4. Test the farm system!")
    else:
        print("\n❌ Database setup failed")
        print("💡 Check the error messages above")