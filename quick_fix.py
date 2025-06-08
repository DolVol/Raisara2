import os
from sqlalchemy import create_engine, text

# Simple database fix for Render deployment
def quick_fix():
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///db.sqlite3')
    
    # Fix for Render PostgreSQL
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            print("🔧 Quick database fix starting...")
            
            # Check if PostgreSQL or SQLite
            is_postgres = 'postgresql' in DATABASE_URL
            
            # Fix dome table - add missing columns
            try:
                if is_postgres:
                    conn.execute(text("ALTER TABLE dome ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    conn.execute(text("ALTER TABLE dome ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE dome ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    conn.execute(text("ALTER TABLE dome ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                print("✅ Fixed dome table")
            except:
                print("ℹ️ Dome table already fixed")
            
            # Fix grid_settings table
            try:
                if is_postgres:
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN IF NOT EXISTS grid_type VARCHAR(20) DEFAULT 'dome'"))
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN IF NOT EXISTS user_id INTEGER"))
                else:
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN grid_type VARCHAR(20) DEFAULT 'dome'"))
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN user_id INTEGER"))
                print("✅ Fixed grid_settings table")
            except:
                print("ℹ️ Grid_settings table already fixed")
            
            conn.commit()
            print("🎉 Quick fix completed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    quick_fix()