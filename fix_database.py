import sqlite3
import os

def fix_database_columns():
    """Add missing columns to the database"""
    
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file 'db.sqlite3' not found!")
        return False
    
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        print("🔄 Fixing database columns...")
        
        # Check current tree table structure
        cursor.execute("PRAGMA table_info(tree)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current tree table columns: {existing_columns}")
        
        # Add missing columns one by one
        columns_to_add = [
            ("image_url", "VARCHAR(200)"),
            ("info", "TEXT"),
            ("life_days", "INTEGER DEFAULT 0"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE tree ADD COLUMN {column_name} {column_type}')
                    print(f"✅ Added {column_name} column to tree table")
                except sqlite3.OperationalError as e:
                    print(f"⚠️ Error adding {column_name} column: {e}")
            else:
                print(f"ℹ️ {column_name} column already exists in tree table")
        
        # Check dome table
        cursor.execute("PRAGMA table_info(dome)")
        dome_columns = [column[1] for column in cursor.fetchall()]
        print(f"📋 Current dome table columns: {dome_columns}")
        
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
            SET life_days = 1, updated_at = CURRENT_TIMESTAMP 
            WHERE life_days IS NULL OR life_days = 0
        ''')
        updated_rows = cursor.rowcount
        print(f"✅ Initialized life_days for {updated_rows} trees")
        
        # Commit all changes
        conn.commit()
        
        # Verify the final structure
        cursor.execute("PRAGMA table_info(tree)")
        final_columns = cursor.fetchall()
        
        print(f"\n📋 Final tree table structure:")
        for column in final_columns:
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
        print(f"\n🎉 Database columns fixed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing database: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting database column fix...")
    success = fix_database_columns()
    
    if success:
        print("\n✅ Database fix completed!")
        print("📝 Next steps:")
        print("   1. Make sure your models.py has all the columns uncommented")
        print("   2. Run your Flask app: python app.py")
        print("   3. Test the life day system")
    else:
        print("\n❌ Database fix failed. Please check the errors above.")