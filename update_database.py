import sqlite3
import os

def inspect_database():
    """Inspect the database to see what tables exist"""
    
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        return None
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("📋 Found tables in database:")
        for table in tables:
            print(f"   - {table[0]}")
        
        # Check for tree-related tables
        tree_table = None
        for table in tables:
            table_name = table[0].lower()
            if 'tree' in table_name:
                tree_table = table[0]
                print(f"🌳 Found tree table: {tree_table}")
                
                # Show table structure
                cursor.execute(f"PRAGMA table_info({tree_table})")
                columns = cursor.fetchall()
                
                print(f"\n📋 Current {tree_table} table structure:")
                for column in columns:
                    print(f"   - {column[1]} ({column[2]})")
                
                # Show sample data
                cursor.execute(f"SELECT COUNT(*) FROM {tree_table}")
                count = cursor.fetchone()[0]
                print(f"\n📊 Total records in {tree_table}: {count}")
                
                if count > 0:
                    cursor.execute(f"SELECT * FROM {tree_table} LIMIT 3")
                    sample_data = cursor.fetchall()
                    print(f"\n📄 Sample data from {tree_table}:")
                    for i, row in enumerate(sample_data, 1):
                        print(f"   Row {i}: {row}")
                
                break
        
        conn.close()
        return tree_table
        
    except Exception as e:
        print(f"❌ Error inspecting database: {e}")
        return None

def update_database(table_name):
    """Add life tracking columns to the specified table"""
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print(f"🔄 Updating {table_name} table schema...")
        
        # Add columns (will fail silently if they already exist)
        try:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN life_days INTEGER DEFAULT 0')
            print("✅ Added life_days column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("ℹ️ life_days column already exists")
            else:
                print(f"⚠️ Error adding life_days column: {e}")
        
        try:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN info TEXT')
            print("✅ Added info column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("ℹ️ info column already exists")
            else:
                print(f"⚠️ Error adding info column: {e}")
        
        try:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            print("✅ Added updated_at column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("ℹ️ updated_at column already exists")
            else:
                print(f"⚠️ Error adding updated_at column: {e}")
        
        # Update existing records with current timestamp
        cursor.execute(f'''
            UPDATE {table_name} 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE updated_at IS NULL
        ''')
        updated_rows = cursor.rowcount
        print(f"✅ Updated {updated_rows} records with current timestamp")
        
        # Initialize life_days to 1 for existing trees (optional)
        cursor.execute(f'''
            UPDATE {table_name} 
            SET life_days = 1 
            WHERE life_days IS NULL OR life_days = 0
        ''')
        initialized_rows = cursor.rowcount
        print(f"✅ Initialized life_days for {initialized_rows} trees")
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        print(f"\n📋 Updated {table_name} table structure:")
        for column in columns:
            print(f"   - {column[1]} ({column[2]})")
        
        # Check how many trees have life_days
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE life_days IS NOT NULL")
        trees_with_life_days = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_trees = cursor.fetchone()[0]
        
        print(f"\n📊 Database status:")
        print(f"   - Total trees: {total_trees}")
        print(f"   - Trees with life_days: {trees_with_life_days}")
        
        # Show sample updated data
        if total_trees > 0:
            cursor.execute(f"SELECT id, name, life_days, updated_at FROM {table_name} LIMIT 3")
            sample_data = cursor.fetchall()
            print(f"\n📄 Sample updated data:")
            for row in sample_data:
                print(f"   ID: {row[0]}, Name: {row[1]}, Life Days: {row[2]}, Updated: {row[3]}")
        
        conn.close()
        print(f"\n🎉 {table_name} table update completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error updating {table_name} table: {e}")
        return False

def create_tree_table_if_missing():
    """Create a basic tree table if none exists"""
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("🔧 Creating basic tree table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tree (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                dome_id INTEGER,
                row INTEGER,
                col INTEGER,
                life_days INTEGER DEFAULT 1,
                info TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dome_id) REFERENCES dome (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Tree table created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating tree table: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting database inspection and migration...")
    
    # First, inspect the database
    tree_table = inspect_database()
    
    if tree_table:
        # Found a tree table, update it
        print(f"\n🔄 Proceeding to update {tree_table} table...")
        success = update_database(tree_table)
    else:
        print("\n❓ No tree table found. Let me check if we should create one...")
        
        # Check if there are any tables at all
        try:
            conn = sqlite3.connect('db.sqlite3')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            all_tables = cursor.fetchall()
            conn.close()
            
            if len(all_tables) == 0:
                print("📝 Database is empty. Creating basic tree table...")
                success = create_tree_table_if_missing()
            else:
                print("⚠️ Database has tables but no tree table found.")
                print("   Available tables:", [table[0] for table in all_tables])
                print("   Please check your models.py to see the correct table name.")
                success = False
                
        except Exception as e:
            print(f"❌ Error checking database: {e}")
            success = False
    
    if success:
        print("\n✅ Database migration completed successfully!")
        print("   You can now run your Flask app with life day functionality!")
        print("   Run: python app.py")
        print("\n🔍 To test the life day system:")
        print("   1. Start your app: python app.py")
        print("   2. Check scheduler status: http://localhost:5000/admin/scheduler_status")
        print("   3. Manual update: POST to http://localhost:5000/admin/update_tree_life")
    else:
        print("\n❌ Database migration failed. Please check the errors above.")
        print("\n🔧 Troubleshooting steps:")
        print("   1. Make sure your Flask app has been run at least once to create tables")
        print("   2. Check your models.py file for the correct table name")
        print("   3. Try running: python app.py first, then run this script again")