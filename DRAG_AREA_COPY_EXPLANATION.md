# Drag Area Copy System Explanation

## Overview
The drag area copy system allows users to copy entire areas of trees from one location to another, preserving plant relationships (mother-cutting pairs) and providing flexible paste options.

## Key Components

### 1. **Area Detection**
When you copy a drag area, the system:
- Finds all trees within the area boundaries using coordinate comparison
- Identifies trees by checking if their `internal_row` and `internal_col` fall within the area's `minRow`, `maxRow`, `minCol`, `maxCol`

```javascript
const treesInArea = trees.filter(tree => {
    const treeRow = parseInt(tree.internal_row);
    const treeCol = parseInt(tree.internal_col);
    return treeRow >= area.minRow && treeRow <= area.maxRow &&
           treeCol >= area.minCol && treeCol <= area.maxCol;
});
```

### 2. **Relationship Analysis**
The system analyzes plant relationships:
- **Mother Trees**: Trees with `plant_type === 'mother'`
- **Cutting Trees**: Trees with `plant_type === 'cutting'` and a `mother_plant_id`
- **Related Trees**: Trees outside the area that have relationships with trees inside the area

### 3. **Clipboard Data Structure**
The copied data includes:
```javascript
{
    id: "clipboard_timestamp",
    type: "dragArea",
    name: "Area Name",
    width: 5,
    height: 3,
    trees: [...], // All trees (area + related)
    tree_count: 15,
    summary: {
        total_trees: 15,
        trees_in_original_area: 10,
        related_trees_outside_area: 5,
        plant_relationships: {
            mother_trees: 3,
            cutting_trees: 7,
            complete_relationships: 3
        }
    }
}
```

### 4. **Storage System**
Data is stored in multiple locations for reliability:
- `window.dragClipboard` - Global JavaScript variable
- `localStorage.globalDragClipboard` - Browser storage for persistence
- `window.clipboardArea` - Compatibility with existing code

## Copy Process Flow

1. **User clicks copy button** on a drag area
2. **System finds trees** within the area bounds
3. **Analyzes relationships** to find related trees outside the area
4. **Creates clipboard data** with all trees and metadata
5. **Stores data** in multiple locations
6. **Shows paste options** dialog

## Paste Options

### 1. **Click to Paste All Trees**
- Pastes all trees (area + related) to maintain relationships
- User clicks on grid to choose position
- Validates position to ensure area fits within grid bounds

### 2. **Manual Position**
- User enters specific row/column coordinates
- Same as click-to-paste but with precise positioning

### 3. **Area Trees Only**
- Pastes only trees that were originally in the selected area
- Excludes related trees outside the area
- May break some plant relationships

### 4. **Area Boundary Only**
- Creates just the area boundary without any trees
- Useful for creating empty areas for future planting

## Tree Creation Process

When pasting, the system:
1. Calculates position offset from original to target location
2. Creates new trees via API calls to `/api/dome/${domeId}/trees`
3. Preserves tree properties: name, breed, plant_type, mother_plant_id, info
4. Updates tree positions based on the offset
5. Handles relationship preservation for mother-cutting pairs

## Error Handling

The system handles various error scenarios:
- **Invalid paste position**: Area extends outside grid bounds
- **Overlapping trees**: Position already occupied (configurable)
- **API failures**: Network errors during tree creation
- **Storage failures**: localStorage quota exceeded

## Visual Feedback

Users receive feedback through:
- **Status messages**: Success/error notifications
- **Visual indicators**: Grid highlighting during paste mode
- **Progress updates**: Tree creation progress
- **Paste button**: Shows clipboard status

## Relationship Preservation

The system preserves plant relationships by:
- Including related trees even if outside the selected area
- Maintaining `mother_plant_id` references
- Providing options to paste with or without relationships
- Warning users about potential relationship breaks

## Usage Example

1. User selects trees in a 3×3 area containing 2 mother trees and 4 cuttings
2. System finds 2 additional cutting trees outside the area related to the mothers
3. Clipboard contains 8 trees total (6 in area + 2 related)
4. User can choose to paste all 8 trees or just the 6 from the area
5. Trees are created at the new location with preserved relationships

## Benefits

- **Relationship Preservation**: Maintains mother-cutting connections
- **Flexible Pasting**: Multiple paste options for different needs
- **Cross-Grid Support**: Copy from one grid and paste to another
- **Persistent Storage**: Clipboard survives page reloads
- **Error Recovery**: Robust error handling and user feedback

## Technical Notes

- Uses modern JavaScript async/await for API calls
- Implements proper event handling for click-to-paste mode
- Provides comprehensive logging for debugging
- Follows consistent naming conventions
- Includes proper cleanup of event listeners and DOM elements