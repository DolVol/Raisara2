#!/usr/bin/env python3
"""
Quick Database Check
"""
import sqlite3
import os

def check_database():
    db_file = 'db.sqlite3'
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Check dome columns
        cursor.execute('PRAGMA table_info(dome);')
        dome_columns = [row[1] for row in cursor.fetchall()]
        print('Dome columns:', dome_columns)
        
        # Check if farm table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='farm';")
        farm_exists = cursor.fetchone()
        print('Farm table exists:', farm_exists is not None)
        
        # Check if farm_id exists in dome table
        has_farm_id = 'farm_id' in dome_columns
        print('Dome has farm_id:', has_farm_id)
        
        if not has_farm_id:
            print("\n❌ PROBLEM: dome.farm_id column is missing!")
            print("🔧 SOLUTION: Run 'python add_farm_table.py' to add it")
        else:
            print("\n✅ Database looks good!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    check_database()