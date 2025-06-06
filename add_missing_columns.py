import sqlite3
import os

def add_missing_columns():
    """Add missing columns to the database tables"""
    
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("🔄 Adding missing columns to database...")
        
        # Check current tree table structure
        cursor.execute("PRAGMA table_info(tree)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current tree table columns: {existing_columns}")
        
        # Add missing columns to tree table
        tree_columns_to_add = [
            ("image_url", "VARCHAR(200)"),
            ("info", "TEXT"),
            ("life_days", "INTEGER DEFAULT 0"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in tree_columns_to_add:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE tree ADD COLUMN {column_name} {column_type}')
                    print(f"✅ Added {column_name} column to tree table")
                except sqlite3.OperationalError as e:
                    print(f"⚠️ Error adding {column_name} to tree table: {e}")
            else:
                print(f"ℹ️ {column_name} column already exists in tree table")
        
        # Check dome table structure
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current dome table columns: {dome_columns}")
        
        # Add missing columns to dome table
        if "image_url" not in dome_columns:
            try:
                cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                print("✅ Added image_url column to dome table")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Error adding image_url to dome table: {e}")
        else:
            print("ℹ️ image_url column already exists in dome table")
        
        # Initialize life_days for existing trees
        cursor.execute('''
            UPDATE tree 
            SET life_days = COALESCE(life_days, 1),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE id IS NOT NULL
        ''')
        updated_rows = cursor.rowcount
        print(f"✅ Initialized data for {updated_rows} trees")
        
        # Commit all changes
        conn.commit()
        
        # Verify the final structure
        cursor.execute("PRAGMA table_info(tree)")
        final_tree_columns = cursor.fetchall()
        
        cursor.execute("PRAGMA table_info(dome)")
        final_dome_columns = cursor.fetchall()
        
        print(f"\n📋 Final tree table structure:")
        for column in final_tree_columns:
            print(f"   - {column[1]} ({column[2]})")
        
        print(f"\n📋 Final dome table structure:")
        for column in final_dome_columns:
            print(f"   - {column[1]} ({column[2]})")
        
        # Show sample data
        cursor.execute("SELECT COUNT(*) FROM tree")
        tree_count = cursor.fetchone()[0]
        print(f"\n📊 Total trees in database: {tree_count}")
        
        if tree_count > 0:
            cursor.execute("SELECT id, name, life_days, updated_at FROM tree LIMIT 3")
            sample_data = cursor.fetchall()
            print(f"\n📄 Sample tree data:")
            for row in sample_data:
                print(f"   ID: {row[0]}, Name: {row[1]}, Life Days: {row[2]}, Updated: {row[3]}")
        
        conn.close()
        print(f"\n🎉 Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting database migration...")
    success = add_missing_columns()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("📝 Next steps:")
        print("   1. Your models.py is already correct")
        print("   2. Run your Flask app: python app.py")
        print("   3. Test the life day system")
        print("\n🔍 To test life day updates:")
        print("   curl -X POST http://localhost:5000/admin/update_tree_life")
    else:
        print("\n❌ Migration failed. Please check the errors above.")