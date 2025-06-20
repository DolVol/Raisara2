#!/usr/bin/env python3
"""
Run Migration on Startup
This script runs the database migration when the app starts up on Render.
"""

import os
import sys
from flask import Flask
from flask_migrate import upgrade
from app import create_app

def run_migration():
    """Run database migration on startup"""
    try:
        print("🚀 Running database migration on startup...")
        
        # Create app instance
        app = create_app()
        
        with app.app_context():
            # Run the migration
            upgrade()
            print("✅ Database migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = run_migration()
    if not success:
        print("⚠️ Migration failed, but continuing with app startup...")
    sys.exit(0)  # Don't fail the startup even if migration fails