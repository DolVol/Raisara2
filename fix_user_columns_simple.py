#!/usr/bin/env python3
"""
Simple User Table Column Fix
This script uses the existing Flask app to add missing columns to the user table.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import Flask app components
try:
    from app import create_app, db
    from sqlalchemy import text
    
    def fix_user_columns():
        """Fix missing user table columns"""
        app = create_app()
        
        with app.app_context():
            try:
                # Check if we're using PostgreSQL or SQLite
                database_url = app.config['SQLALCHEMY_DATABASE_URI']
                is_postgresql = 'postgresql' in database_url or 'postgres' in database_url
                
                print(f"🔗 Database: {'PostgreSQL' if is_postgresql else 'SQLite'}")
                
                # Get current columns
                if is_postgresql:
                    result = db.session.execute(text("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'user'
                    """))
                else:
                    result = db.session.execute(text("PRAGMA table_info(user)"))
                
                if is_postgresql:
                    current_columns = [row[0] for row in result.fetchall()]
                else:
                    current_columns = [row[1] for row in result.fetchall()]
                
                print(f"📋 Current user table columns: {current_columns}")
                
                # Define required columns
                required_columns = ['last_login', 'previous_login', 'login_count']
                missing_columns = [col for col in required_columns if col not in current_columns]
                
                if not missing_columns:
                    print("✅ All required columns already exist")
                    return True
                
                print(f"🔧 Missing columns to add: {missing_columns}")
                
                # Add missing columns
                for column in missing_columns:
                    try:
                        if is_postgresql:
                            # PostgreSQL syntax
                            if column == 'login_count':
                                sql = f'ALTER TABLE "user" ADD COLUMN {column} INTEGER DEFAULT 0'
                            else:
                                sql = f'ALTER TABLE "user" ADD COLUMN {column} TIMESTAMP'
                        else:
                            # SQLite syntax
                            if column == 'login_count':
                                sql = f'ALTER TABLE user ADD COLUMN {column} INTEGER DEFAULT 0'
                            else:
                                sql = f'ALTER TABLE user ADD COLUMN {column} DATETIME'
                        
                        print(f"🔧 Adding column {column}: {sql}")
                        db.session.execute(text(sql))
                        db.session.commit()
                        print(f"✅ Successfully added column: {column}")
                        
                    except Exception as col_error:
                        print(f"❌ Error adding column {column}: {col_error}")
                        db.session.rollback()
                        return False
                
                print("✅ All missing columns added successfully!")
                return True
                
            except Exception as e:
                print(f"❌ Database error: {e}")
                db.session.rollback()
                return False
    
    def main():
        """Main function"""
        print("🚀 Starting User Table Column Fix (Simple Version)")
        print("=" * 60)
        
        success = fix_user_columns()
        
        print("=" * 60)
        if success:
            print("✅ User table column fix completed successfully!")
            print("🎉 You can now try logging in/registering again")
        else:
            print("❌ User table column fix failed")
            print("💡 Check the error messages above for details")
        
        return success

    if __name__ == "__main__":
        success = main()
        sys.exit(0 if success else 1)
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure you're running this from the correct directory with the right Python environment")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)