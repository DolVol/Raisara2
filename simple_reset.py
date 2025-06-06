import sqlite3
import os

def manual_fix():
    if not os.path.exists('db.sqlite3'):
        print("No database found. Please run simple_reset.py first.")
        return
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("Checking and fixing database columns...")
        
        # Check dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Dome table columns: {dome_columns}")
        
        # Add missing columns to dome table
        if 'image_url' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
            print("✓ Added image_url to dome table")
        
        if 'grid_row' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN grid_row INTEGER DEFAULT 0')
            print("✓ Added grid_row to dome table")
        
        if 'grid_col' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN grid_col INTEGER DEFAULT 0')
            print("✓ Added grid_col to dome table")
        
        if 'internal_rows' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN internal_rows INTEGER DEFAULT 10')
            print("✓ Added internal_rows to dome table")
        
        if 'internal_cols' not in dome_columns:
            cursor.execute('ALTER TABLE dome ADD COLUMN internal_cols INTEGER DEFAULT 10')
            print("✓ Added internal_cols to dome table")
        
        # Check tree table
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"Tree table columns: {tree_columns}")
        
        # Add missing columns to tree table
        if 'image_url' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
            print("✓ Added image_url to tree table")
        
        if 'info' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
            print("✓ Added info to tree table")
        
        if 'life_days' not in tree_columns:
            cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
            print("✓ Added life_days to tree table")
        
        # Check if grid_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grid_settings'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE grid_settings (
                    id INTEGER PRIMARY KEY,
                    rows INTEGER DEFAULT 5,
                    cols INTEGER DEFAULT 5
                )
            ''')
            cursor.execute('INSERT INTO grid_settings (rows, cols) VALUES (5, 5)')
            print("✓ Created grid_settings table")
        
        conn.commit()
        conn.close()
        
        print("\n🎉 Database fixed successfully!")
        print("You can now run: python app.py")
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")

if __name__ == '__main__':
    manual_fix()