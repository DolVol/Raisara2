import sqlite3
import os

def fix_missing_tables():
    """Check existing tables and create missing ones"""
    
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("🔍 Checking existing tables...")
        
        # Get all existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [table[0] for table in cursor.fetchall()]
        print(f"📋 Existing tables: {existing_tables}")
        
        # ===== CREATE DOME TABLE IF MISSING =====
        if 'dome' not in existing_tables:
            print("\n🔧 Creating dome table...")
            cursor.execute('''
                CREATE TABLE dome (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL,
                    image_url VARCHAR(200),
                    grid_row INTEGER DEFAULT 0,
                    grid_col INTEGER DEFAULT 0,
                    internal_rows INTEGER DEFAULT 10,
                    internal_cols INTEGER DEFAULT 10,
                    x INTEGER DEFAULT 0,
                    y INTEGER DEFAULT 0,
                    row INTEGER DEFAULT 0,
                    col INTEGER DEFAULT 0
                )
            ''')
            print("✅ Created dome table")
            
            # Add a default dome for testing
            cursor.execute('''
                INSERT INTO dome (name, grid_row, grid_col, internal_rows, internal_cols)
                VALUES ('Default Dome', 0, 0, 10, 10)
            ''')
            print("✅ Added default dome")
        else:
            print("ℹ️ dome table already exists")
            
            # Check if dome table has image_url column
            cursor.execute("PRAGMA table_info(dome)")
            dome_columns = [column[1] for column in cursor.fetchall()]
            print(f"📋 Current dome columns: {dome_columns}")
            
            if "image_url" not in dome_columns:
                try:
                    cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                    print("✅ Added image_url to existing dome table")
                except sqlite3.OperationalError as e:
                    print(f"⚠️ Error adding image_url to dome: {e}")
        
        # ===== CREATE GRID_SETTINGS TABLE IF MISSING =====
        if 'grid_settings' not in existing_tables:
            print("\n🔧 Creating grid_settings table...")
            cursor.execute('''
                CREATE TABLE grid_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rows INTEGER DEFAULT 5,
                    cols INTEGER DEFAULT 5
                )
            ''')
            print("✅ Created grid_settings table")
            
            # Add default grid settings
            cursor.execute('''
                INSERT INTO grid_settings (rows, cols)
                VALUES (5, 5)
            ''')
            print("✅ Added default grid settings")
        else:
            print("ℹ️ grid_settings table already exists")
        
        # ===== CHECK TREE TABLE =====
        if 'tree' in existing_tables:
            cursor.execute("PRAGMA table_info(tree)")
            tree_columns = [column[1] for column in cursor.fetchall()]
            print(f"📋 Tree table columns: {tree_columns}")
            
            # Ensure tree table has all required columns
            tree_columns_to_add = [
                ("image_url", "VARCHAR(200)"),
                ("info", "TEXT"),
                ("life_days", "INTEGER DEFAULT 0"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            ]
            
            for column_name, column_type in tree_columns_to_add:
                if column_name not in tree_columns:
                    try:
                        cursor.execute(f'ALTER TABLE tree ADD COLUMN {column_name} {column_type}')
                        print(f"✅ Added {column_name} to tree table")
                    except sqlite3.OperationalError as e:
                        print(f"⚠️ Error adding {column_name} to tree: {e}")
        else:
            print("\n🔧 Creating tree table...")
            cursor.execute('''
                CREATE TABLE tree (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL,
                    image_url VARCHAR(200),
                    dome_id INTEGER,
                    row INTEGER DEFAULT 0,
                    col INTEGER DEFAULT 0,
                    info TEXT,
                    life_days INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dome_id) REFERENCES dome (id)
                )
            ''')
            print("✅ Created tree table")
        
        # ===== INITIALIZE DATA =====
        print("\n🔄 Initializing data...")
        
        # Initialize tree life_days for existing trees
        cursor.execute('''
            UPDATE tree 
            SET life_days = COALESCE(life_days, 1),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE id IS NOT NULL
        ''')
        tree_updates = cursor.rowcount
        print(f"✅ Initialized data for {tree_updates} trees")
        
        # Commit all changes
        conn.commit()
        
        # ===== FINAL VERIFICATION =====
        print("\n📋 Final verification...")
        
        # Check all tables again
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        final_tables = [table[0] for table in cursor.fetchall()]
        print(f"📋 Final tables: {final_tables}")
        
        # Show table structures
        for table_name in ['dome', 'tree', 'grid_settings']:
            if table_name in final_tables:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                print(f"\n📋 {table_name} table structure:")
                for column in columns:
                    print(f"   - {column[1]} ({column[2]})")
        
        # Show counts
        cursor.execute("SELECT COUNT(*) FROM dome")
        dome_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tree")
        tree_count = cursor.fetchone()[0]
        
        print(f"\n📊 Database summary:")
        print(f"   - Total domes: {dome_count}")
        print(f"   - Total trees: {tree_count}")
        
        # Show sample data
        if dome_count > 0:
            cursor.execute("SELECT id, name, grid_row, grid_col FROM dome LIMIT 3")
            sample_domes = cursor.fetchall()
            print(f"\n📄 Sample dome data:")
            for row in sample_domes:
                print(f"   ID: {row[0]}, Name: {row[1]}, Grid: ({row[2]}, {row[3]})")
        
        if tree_count > 0:
            cursor.execute("SELECT id, name, life_days, dome_id FROM tree LIMIT 3")
            sample_trees = cursor.fetchall()
            print(f"\n📄 Sample tree data:")
            for row in sample_trees:
                print(f"   ID: {row[0]}, Name: {row[1]}, Life Days: {row[2]}, Dome ID: {row[3]}")
        
        conn.close()
        print(f"\n🎉 Database setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting complete database setup...")
    success = fix_missing_tables()
    
    if success:
        print("\n✅ Database setup completed successfully!")
        print("📝 Your database now has all required tables and columns!")
        print("🚀 You can now run: python app.py")
        print("\n🔍 To test the life day system:")
        print("   1. Start your app: python app.py")
        print("   2. Visit: http://localhost:5000")
        print("   3. Test life day update: curl -X POST http://localhost:5000/admin/update_tree_life")
    else:
        print("\n❌ Database setup failed. Please check the errors above.")