#!/usr/bin/env python3
"""
Add enhanced debugging to the paste function to see what's happening with relationships.
"""

import re

def add_debugging_to_paste_function():
    """Add debugging to the _create_trees_with_relationships function"""
    
    # Read the current app.py file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add debugging at the start of the function
    pattern1 = r'(print\(f"🌱 Creating \{len\(copied_area\[\'trees\'\]\)\} trees from copied area\.\.\."\))'
    
    replacement1 = r'''\1

    # ✅ ENHANCED DEBUG: Show what data we're working with
    print(f"🔍 === DEBUGGING PASTE OPERATION ===")
    print(f"📊 Trees to create: {len(copied_area.get('trees', []))}")
    
    for i, tree_data in enumerate(copied_area.get('trees', [])):
        print(f"🌳 Tree {i}: '{tree_data.get('name', 'Unknown')}'")
        print(f"   - Plant type: {tree_data.get('plant_type', 'Unknown')}")
        print(f"   - Mother plant ID: {tree_data.get('mother_plant_id', 'None')}")
        print(f"   - Original ID: {tree_data.get('id', 'None')}")
        print(f"   - Has mother_plant_id key: {'mother_plant_id' in tree_data}")
        print(f"   - All keys: {list(tree_data.keys())}")
    
    print(f"🔍 === END PASTE DEBUG INFO ===")'''
    
    if re.search(pattern1, content):
        content = re.sub(pattern1, replacement1, content)
        print("✅ Added debugging to paste function start")
    else:
        print("⚠️ Could not find paste function start pattern")
    
    # Add debugging to the tree creation loop
    pattern2 = r'(# Plant relationship handling\s*plant_type = tree_data\.get\(\'plant_type\', \'mother\'\))'
    
    replacement2 = r'''\1
        cutting_notes = tree_data.get('cutting_notes', '')
        original_mother_id = tree_data.get('mother_plant_id')  # ✅ CRITICAL: Capture this!
        
        # ✅ DEBUG: Log what we're working with for each tree
        print(f"🌱 Creating tree {i}: '{tree_data.get('name', 'Unknown')}'")
        print(f"   - Plant type: {plant_type}")
        print(f"   - Original mother ID: {original_mother_id}")
        print(f"   - Original tree ID: {tree_data.get('id')}")
        print(f"   - Tree data keys: {list(tree_data.keys())}")'''
    
    if re.search(pattern2, content):
        content = re.sub(pattern2, replacement2, content)
        print("✅ Added debugging to tree creation loop")
    else:
        print("⚠️ Could not find tree creation loop pattern")
    
    # Add debugging to the relationship processing
    pattern3 = r'(# ✅ ENHANCED: Second pass - Comprehensive relationship mapping with better debugging)'
    
    replacement3 = r'''\1
    print(f"🔗 === STARTING RELATIONSHIP PROCESSING ===")
    print(f"🔗 Original to new ID mapping: {dict(list(original_to_new_id_mapping.items())[:5])}...")  # Show first 5
    print(f"🔗 Mother ID mapping: {dict(list(mother_id_mapping.items())[:5])}...")  # Show first 5'''
    
    if re.search(pattern3, content):
        content = re.sub(pattern3, replacement3, content)
        print("✅ Added debugging to relationship processing")
    else:
        print("⚠️ Could not find relationship processing pattern")
    
    # Write the updated content back to app.py
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n✅ Enhanced debugging added to paste function")
    print("\nNow test the copy/paste operation and check the console logs for:")
    print("1. What data is captured during copy")
    print("2. What data is processed during paste")
    print("3. Whether mother_plant_id is preserved")
    print("4. Whether relationship mapping is working")

if __name__ == "__main__":
    add_debugging_to_paste_function()