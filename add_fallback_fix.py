#!/usr/bin/env python3
"""
Add the fallback relationship fix to the end of _create_trees_with_relationships function.
"""

import re

def add_fallback_fix():
    """Add fallback relationship fix"""
    
    # Read the current app.py file
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the return statement at the end of _create_trees_with_relationships
    pattern = r'(return \{\s*\'new_tree_ids\': new_tree_ids,\s*\'trees_created\': trees_created,\s*\'breed_debug_info\': breed_debug_info,\s*\'relationship_stats\': relationship_stats\s*\})'
    
    replacement = r'''# ✅ FALLBACK: Final pass to catch any missed relationships
    print("🔄 Final pass: Checking for any missed relationships...")
    
    for tree_id in new_tree_ids:
        tree = Tree.query.get(tree_id)
        if tree and tree.plant_type == 'cutting' and not tree.mother_plant_id:
            # Try to get original_mother_id from paste metadata
            paste_meta = tree.get_paste_metadata()
            original_mother_id = paste_meta.get('original_mother_id')
            
            if original_mother_id:
                print(f"🔄 Fallback: Trying to fix relationship for tree {tree.id} -> mother {original_mother_id}")
                
                # Try to find the mother tree
                mother_tree = None
                
                # Check if mother was also pasted (in our mappings)
                for key_variant in [str(original_mother_id), original_mother_id]:
                    if key_variant in original_to_new_id_mapping:
                        mother_tree = Tree.query.get(original_to_new_id_mapping[key_variant])
                        if mother_tree:
                            print(f"✅ Fallback: Found pasted mother {mother_tree.id}")
                            break
                
                # Check if mother exists in dome
                if not mother_tree:
                    mother_tree = Tree.query.filter_by(
                        id=original_mother_id,
                        dome_id=dome_id,
                        user_id=user_id
                    ).first()
                    if mother_tree:
                        print(f"✅ Fallback: Found existing mother {mother_tree.id}")
                
                # Set the relationship
                if mother_tree and (mother_tree.plant_type == 'mother' or not mother_tree.plant_type):
                    tree.mother_plant_id = mother_tree.id
                    relationship_stats['relationships_preserved'] += 1
                    
                    # Update metadata
                    paste_meta['relationship_preserved'] = True
                    paste_meta['relationship_fixed_in_fallback'] = True
                    tree.set_paste_metadata(paste_meta)
                    
                    print(f"✅ Fallback: Fixed relationship {tree.name} -> {mother_tree.name}")
                else:
                    print(f"❌ Fallback: Could not find valid mother for tree {tree.id}")

    \1'''
    
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        print("✅ Added fallback relationship fix")
    else:
        print("⚠️ Could not find return statement pattern")
        # Try a simpler pattern
        simple_pattern = r'(return \{[^}]*\'relationship_stats\': relationship_stats[^}]*\})'
        if re.search(simple_pattern, content):
            content = re.sub(simple_pattern, replacement, content)
            print("✅ Added fallback fix with simple pattern")
        else:
            print("❌ Could not find any suitable pattern to add fallback fix")
    
    # Write the updated content back to app.py
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n✅ Fallback relationship fix added!")

if __name__ == "__main__":
    add_fallback_fix()