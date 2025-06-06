import sqlite3
import os

def fix_database_simple():
    """Simple fix for missing database columns"""
    
    if not os.path.exists('db.sqlite3'):
        print("Database file 'db.sqlite3' not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("Checking existing tables...")
        
        # Get all existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [table[0] for table in cursor.fetchall()]
        print(f"Existing tables: {existing_tables}")
        
        # Fix dome table
        if 'dome' in existing_tables:
            print("Checking dome table...")
            cursor.execute("PRAGMA table_info(dome)")
            dome_columns = [column[1] for column in cursor.fetchall()]
            print(f"Current dome columns: {dome_columns}")
            
            if "image_url" not in dome_columns:
                try:
                    cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                    print("Added image_url to dome table")
                except sqlite3.OperationalError as e:
                    print(f"Error adding image_url to dome: {e}")
            else:
                print("image_url already exists in dome table")
        else:
            print("Creating dome table...")
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
            print("Created dome table")
            
            # Add a default dome
            cursor.execute('''
                INSERT INTO dome (name, grid_row, grid_col, internal_rows, internal_cols)
                VALUES ('Default Dome', 0, 0, 10, 10)
            ''')
            print("Added default dome")
        
        # Fix tree table
        if 'tree' in existing_tables:
            print("Checking tree table...")
            cursor.execute("PRAGMA table_info(tree)")
            tree_columns = [column[1] for column in cursor.fetchall()]
            print(f"Current tree columns: {tree_columns}")
            
            # Add missing columns to tree table
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
                        print(f"Added {column_name} to tree table")
                    except sqlite3.OperationalError as e:
                        print(f"Error adding {column_name} to tree: {e}")
                else:
                    print(f"{column_name} already exists in tree table")
        
        # Create grid_settings table if missing
        if 'grid_settings' not in existing_tables:
            print("Creating grid_settings table...")
            cursor.execute('''
                CREATE TABLE grid_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rows INTEGER DEFAULT 5,
                    cols INTEGER DEFAULT 5
                )
            ''')
            cursor.execute('INSERT INTO grid_settings (rows, cols) VALUES (5, 5)')
            print("Created grid_settings table")
        
        # Initialize tree data
        cursor.execute('''
            UPDATE tree 
            SET life_days = COALESCE(life_days, 1),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE id IS NOT NULL
        ''')
        tree_updates = cursor.rowcount
        print(f"Initialized data for {tree_updates} trees")
        
        # Commit all changes
        conn.commit()
        
        # Final verification
        print("\nFinal verification...")
        
        # Check dome table structure
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = cursor.fetchall()
        print("Dome table structure:")
        for column in dome_columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # Check tree table structure
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = cursor.fetchall()
        print("Tree table structure:")
        for column in tree_columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # Show counts
        cursor.execute("SELECT COUNT(*) FROM dome")
        dome_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tree")
        tree_count = cursor.fetchone()[0]
        
        print(f"\nDatabase summary:")
        print(f"  - Total domes: {dome_count}")
        print(f"  - Total trees: {tree_count}")
        
        conn.close()
        print("\nDatabase fix completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during fix: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting database fix...")
    success = fix_database_simple()
    
    if success:
        print("\nDatabase fix completed successfully!")
        print("You can now run: python app.py")
        print("\nTo test the life day system:")
        print("  1. Start your app: python app.py")
        print("  2. Visit: http://localhost:5000")
        print("  3. Test life day update: curl -X POST http://localhost:5000/admin/update_tree_life")
    else:
        print("\nDatabase fix failed. Please check the errors above.")