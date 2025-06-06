import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# Check if trees exist
cursor.execute("SELECT COUNT(*) FROM tree")
tree_count = cursor.fetchone()[0]
print(f"Total trees in database: {tree_count}")

# Check table structure
cursor.execute("PRAGMA table_info(tree)")
columns = cursor.fetchall()
print("Tree table columns:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# Check if life_days column exists
has_life_days = any(col[1] == 'life_days' for col in columns)
print(f"Has life_days column: {has_life_days}")

if tree_count > 0:
    cursor.execute("SELECT id, name, life_days FROM tree LIMIT 5")
    trees = cursor.fetchall()
    print("Sample trees:")
    for tree in trees:
        print(f"  ID: {tree[0]}, Name: {tree[1]}, Life Days: {tree[2]}")

conn.close()