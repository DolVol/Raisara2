import os
import shutil
import sqlite3

def complete_reset():
    print("=== COMPLETE DATABASE RESET ===")
    print("This will:")
    print("1. Delete the existing database")
    print("2. Remove migrations folder")
    print("3. Create uploads folder")
    print("4. Create a fresh database with all required tables and columns")
    print("\nWARNING: ALL EXISTING DATA WILL BE LOST!")
    
    confirm = input("\nDo you want to continue? Type 'YES' to confirm: ").strip()
    
    if confirm != 'YES':
        print("Reset cancelled.")
        return False
    
    try:
        print("\n🔄 Starting reset process...")
        
        # Step 1: Remove existing database
        if os.path.exists('db.sqlite3'):
            os.remove('db.sqlite3')
            print("✓ Removed existing database")
        else:
            print("ℹ No existing database found")
        
        # Step 2: Remove migrations folder
        if os.path.exists('migrations'):
            shutil.rmtree('migrations')
            print("✓ Removed migrations folder")
        else:
            print("ℹ No migrations folder found")
        
        # Step 3: Create uploads folder
        if not os.path.exists('uploads'):
            os.makedirs('uploads')
            print("✓ Created uploads folder")
        else:
            print("ℹ Uploads folder already exists")
        
        # Step 4: Create new database with all required tables
        print("🔨 Creating new database...")
        
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # Create grid_settings table
        cursor.execute('''
            CREATE TABLE grid_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rows INTEGER DEFAULT 5,
                cols INTEGER DEFAULT 5
            )
        ''')
        print("✓ Created grid_settings table")
        
        # Create dome table with ALL required columns
        cursor.execute('''
            CREATE TABLE dome (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100),
                image_url VARCHAR(200),
                grid_row INTEGER DEFAULT 0,
                grid_col INTEGER DEFAULT 0,
                internal_rows INTEGER DEFAULT 10,
                internal_cols INTEGER DEFAULT 10,
                x INTEGER DEFAULT 0,
                y INTEGER DEFAULT 0,
                "row" INTEGER DEFAULT 0,
                col INTEGER DEFAULT 0
            )
        ''')
        print("✓ Created dome table with image_url column")
        
        # Create row table
        cursor.execute('''
            CREATE TABLE "row" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100),
                dome_id INTEGER,
                FOREIGN KEY (dome_id) REFERENCES dome(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created row table")
        
        # Create tree table with ALL required columns
        cursor.execute('''
            CREATE TABLE tree (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100),
                image_url VARCHAR(200),
                dome_id INTEGER,
                "row" INTEGER DEFAULT 0,
                col INTEGER DEFAULT 0,
                info TEXT,
                life_days INTEGER DEFAULT 0,
                FOREIGN KEY (dome_id) REFERENCES dome(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created tree table with image_url, info, and life_days columns")
        
        # Insert default grid settings
        cursor.execute('INSERT INTO grid_settings (rows, cols) VALUES (5, 5)')
        print("✓ Added default grid settings (5x5)")
        
        # Commit all changes
        conn.commit()
        conn.close()
        
        print("\n🎉 DATABASE RESET COMPLETED SUCCESSFULLY!")
        print("\nDatabase structure:")
        print("- grid_settings: id, rows, cols")
        print("- dome: id, name, image_url, grid_row, grid_col, internal_rows, internal_cols, x, y, row, col")
        print("- row: id, name, dome_id")
        print("- tree: id, name, image_url, dome_id, row, col, info, life_days")
        print("\n✅ You can now run: python app.py")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR during reset: {e}")
        print("Please check the error and try again.")
        return False

def verify_database():
    """Verify that the database has all required columns"""
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("\n🔍 Verifying database structure...")
        
        # Check dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Dome table columns: {dome_columns}")
        
        required_dome_columns = ['id', 'name', 'image_url', 'grid_row', 'grid_col', 'internal_rows', 'internal_cols']
        missing_dome = [col for col in required_dome_columns if col not in dome_columns]
        
        if missing_dome:
            print(f"❌ Missing dome columns: {missing_dome}")
            return False
        else:
            print("✅ Dome table has all required columns")
        
        # Check tree table
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"Tree table columns: {tree_columns}")
        
        required_tree_columns = ['id', 'name', 'image_url', 'dome_id', 'row', 'col', 'info', 'life_days']
        missing_tree = [col for col in required_tree_columns if col not in tree_columns]
        
        if missing_tree:
            print(f"❌ Missing tree columns: {missing_tree}")
            return False
        else:
            print("✅ Tree table has all required columns")
        
        # Check grid_settings table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grid_settings'")
        if not cursor.fetchone():
            print("❌ Missing grid_settings table")
            return False
        else:
            print("✅ Grid_settings table exists")
        
        conn.close()
        print("\n✅ Database verification passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False

if __name__ == '__main__':
    print("Choose an option:")
    print("1. Complete database reset (recommended)")
    print("2. Verify current database structure")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "1":
        if complete_reset():
            verify_database()
    elif choice == "2":
        verify_database()
    else:
        print("Invalid choice. Please run the script again.")