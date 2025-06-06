import sqlite3
import os

def fix_all_database_columns():
    """Add all missing columns to both tree and dome tables"""
    
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("🔄 Fixing all database columns...")
        
        # ===== FIX TREE TABLE =====
        print("\n📋 Checking tree table...")
        cursor.execute("PRAGMA table_info(tree)")
        tree_columns = [column[1] for column in cursor.fetchall()]
        print(f"Current tree columns: {tree_columns}")
        
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
                print(f"ℹ️ {column_name} already exists in tree table")
        
        # ===== FIX DOME TABLE =====
        print("\n📋 Checking dome table...")
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"Current dome columns: {dome_columns}")
        
        if "image_url" not in dome_columns:
            try:
                cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                print("✅ Added image_url to dome table")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Error adding image_url to dome: {e}")
        else:
            print("ℹ️ image_url already exists in dome table")
        
        # ===== INITIALIZE DATA =====
        print("\n🔄 Initializing data...")
        
        # Initialize tree data
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
        
        # ===== VERIFY RESULTS =====
        print("\n📋 Final verification...")
        
        cursor.execute("PRAGMA table_info(tree)")
        final_tree_columns = cursor.fetchall()
        print(f"\nFinal tree table structure:")
        for column in final_tree_columns:
            print(f"   - {column[1]} ({column[2]})")
        
        cursor.execute("PRAGMA table_info(dome)")
        final_dome_columns = cursor.fetchall()
        print(f"\nFinal dome table structure:")
        for column in final_dome_columns:
            print(f"   - {column[1]} ({column[2]})")
        
        # Show counts
        cursor.execute("SELECT COUNT(*) FROM tree")
        tree_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dome")
        dome_count = cursor.fetchone()[0]
        
        print(f"\n📊 Database summary:")
        print(f"   - Total trees: {tree_count}")
        print(f"   - Total domes: {dome_count}")
        
        # Show sample data
        if tree_count > 0:
            cursor.execute("SELECT id, name, life_days, updated_at FROM tree LIMIT 3")
            sample_trees = cursor.fetchall()
            print(f"\n📄 Sample tree data:")
            for row in sample_trees:
                print(f"   ID: {row[0]}, Name: {row[1]}, Life Days: {row[2]}, Updated: {row[3]}")
        
        if dome_count > 0:
            cursor.execute("SELECT id, name, image_url FROM dome LIMIT 3")
            sample_domes = cursor.fetchall()
            print(f"\n📄 Sample dome data:")
            for row in sample_domes:
                print(f"   ID: {row[0]}, Name: {row[1]}, Image URL: {row[2]}")
        
        conn.close()
        print(f"\n🎉 Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting complete database migration...")
    success = fix_all_database_columns()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("📝 Your database now has all required columns!")
        print("🚀 You can now run: python app.py")
        print("\n🔍 To test the life day system:")
        print("   curl -X POST http://localhost:5000/admin/update_tree_life")
    else:
        print("\n❌ Migration failed. Please check the errors above.")