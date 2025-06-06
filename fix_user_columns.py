import sqlite3

# Connect to database
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

print("Adding missing user_id columns...")

# Add user_id columns to existing tables
try:
    cursor.execute('ALTER TABLE grid_settings ADD COLUMN user_id INTEGER')
    print("Added user_id to grid_settings")
except:
    print("user_id already exists in grid_settings")

try:
    cursor.execute('ALTER TABLE dome ADD COLUMN user_id INTEGER')
    print("Added user_id to dome")
except:
    print("user_id already exists in dome")

try:
    cursor.execute('ALTER TABLE tree ADD COLUMN user_id INTEGER')
    print("Added user_id to tree")
except:
    print("user_id already exists in tree")

# Create user table if it doesn't exist
try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(200) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    print("Created user table")
except:
    print("User table already exists")

conn.commit()
conn.close()

print("Database fix completed!")