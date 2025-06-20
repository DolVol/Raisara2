#!/usr/bin/env python3
"""
Auto Database Fix - Runs automatically on app startup
This script fixes the missing user table columns automatically when the app starts.
"""

import os
from complete_db_fix import complete_database_fix

def auto_fix_user_table():
    """Automatically fix missing database columns on startup"""
    
    # Only run on Render (production)
    if not os.getenv('RENDER'):
        print("ℹ️ Auto-fix skipped (not on Render)")
        return True
    
    print("🔧 Running comprehensive database fix...")
    return complete_database_fix()

if __name__ == "__main__":
    auto_fix_user_table()