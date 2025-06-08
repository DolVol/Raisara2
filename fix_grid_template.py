import os

def fix_grid_template():
    """Fix grid.html template to use trees_data instead of trees"""
    
    grid_file = 'templates/grid.html'
    
    if not os.path.exists(grid_file):
        print(f"❌ {grid_file} not found!")
        return False
    
    try:
        # Read the file
        with open(grid_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count occurrences before replacement
        old_count = content.count('{{ trees|tojson|safe }}')
        old_count2 = content.count('trees|tojson')
        
        print(f"🔍 Found {old_count} instances of '{{ trees|tojson|safe }}'")
        print(f"🔍 Found {old_count2} instances of 'trees|tojson'")
        
        # Replace all instances
        content = content.replace('{{ trees|tojson|safe }}', '{{ trees_data|tojson|safe }}')
        content = content.replace('trees|tojson', 'trees_data|tojson')
        
        # Count after replacement
        new_count = content.count('{{ trees_data|tojson|safe }}')
        new_count2 = content.count('trees_data|tojson')
        
        # Write back to file
        with open(grid_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Replaced with {new_count} instances of '{{ trees_data|tojson|safe }}'")
        print(f"✅ Total trees_data|tojson instances: {new_count2}")
        print(f"✅ Fixed {grid_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing template: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Fixing grid.html template...")
    success = fix_grid_template()
    
    if success:
        print("\n✅ Template fixed successfully!")
        print("🚀 You can now restart your app and try 'Back to Grid'")
    else:
        print("\n❌ Template fix failed.")