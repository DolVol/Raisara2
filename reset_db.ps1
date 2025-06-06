# Remove migrations folder and database file
Remove-Item -Recurse -Force migrations -ErrorAction SilentlyContinue
Remove-Item -Force db.sqlite3 -ErrorAction SilentlyContinue

# Initialize fresh migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

Write-Host "Database reset complete!"