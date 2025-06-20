# Cutting Tree Duplication Fix

## Problem Identified
When copying a mother tree with 16 cutting trees and pasting it:
- **Expected**: New mother with 16 cutting trees, old mother with 0
- **Actual**: New mother with 32 cutting trees (16 + 16 duplicates)

## Root Cause
The system is double-counting cutting trees:

1. **Copy Operation**: Auto-includes all 16 cutting trees in clipboard data
2. **Paste Operation**: 
   - Creates 16 new cutting trees from clipboard data
   - Then transfers ALL 16 original cutting trees from old mother to new mother
   - Result: 32 cutting trees (16 new + 16 transferred)

## Solution Applied
Modified the transfer logic to prevent duplication by only transferring cutting trees that were NOT already copied.

### Key Changes in app.py:

```python
# Before (causing duplicates):
for old_cutting in all_old_cuttings:
    # Transfer ALL cutting trees to new mother
    old_cutting.mother_plant_id = mother['new_id']

# After (preventing duplicates):
for old_cutting in all_old_cuttings:
    cutting_was_copied = any(c['old_id'] == old_cutting.id for c in cutting_trees_pasted)
    
    if not cutting_was_copied:
        # Only transfer if NOT copied
        old_cutting.mother_plant_id = mother['new_id']
    else:
        # Remove original since copy exists
        old_cutting.mother_plant_id = None
        old_cutting.plant_type = 'mother'  # Convert to independent
```

## Expected Behavior After Fix
When copying a mother tree with 16 cutting trees:

1. **Copy**: 16 cutting trees included in clipboard
2. **Paste**: 16 new cutting trees created and linked to new mother
3. **Transfer**: Original 16 cutting trees removed from old mother (converted to independent)
4. **Result**: 
   - New mother: 16 cutting trees
   - Old mother: 0 cutting trees
   - Total: 16 cutting trees (no duplicates)

## Status
✅ **IMPLEMENTED** - The fix prevents cutting tree duplication during mother tree copy/paste operations.