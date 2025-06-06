import sqlite3
import os

def add_image_columns():
    # Find the database file
    db_paths = ['instance/db.sqlite3', 'db.sqlite3']
    db_path = None
    
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print("❌ Database file not found!")
        return
    
    print(f"📍 Found database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current table structure
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current tree columns: {tree_columns}")
        
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current dome columns: {dome_columns}")
        
        # Add image_url column to tree table if it doesn't exist
        if 'image_url' not in tree_columns:
            try:
                cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
                print("✅ Added image_url column to tree table")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Error adding image_url to tree: {e}")
        else:
            print("✅ image_url column already exists in tree table")
        
        # Add image_url column to dome table if it doesn't exist
        if 'image_url' not in dome_columns:
            try:
                cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                print("✅ Added image_url column to dome table")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Error adding image_url to dome: {e}")
        else:
            print("✅ image_url column already exists in dome table")
        
        conn.commit()
        print("✅ Database migration completed!")
        
        # Verify columns were added
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns_after = [column[1] for column in cursor.fetchall()]
        print(f"📋 Tree columns after migration: {tree_columns_after}")
        
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns_after = [column[1] for column in cursor.fetchall()]
        print(f"📋 Dome columns after migration: {dome_columns_after}")
        
        # Test inserting a sample image URL
        cursor.execute("SELECT id FROM tree LIMIT 1")
        tree_result = cursor.fetchone()
        if tree_result:
            tree_id = tree_result[0]
            cursor.execute("UPDATE tree SET image_url = ? WHERE id = ?", ('/uploads/test.jpg', tree_id))
            print(f"✅ Test: Updated tree {tree_id} with sample image URL")
            
            # Verify the update worked
            cursor.execute("SELECT image_url FROM tree WHERE id = ?", (tree_id,))
            result = cursor.fetchone()
            if result and result[0]:
                print(f"✅ Test successful: Retrieved image_url = {result[0]}")
                # Clean up test data
                cursor.execute("UPDATE tree SET image_url = NULL WHERE id = ?", (tree_id,))
            else:
                print("❌ Test failed: Could not retrieve image_url")
        
        conn.commit()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    add_image_columns()