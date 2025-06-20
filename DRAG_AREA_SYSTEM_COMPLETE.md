# Complete Drag Area Copy & Paste System

## Overview
Your drag area copy system is now fully integrated and provides comprehensive functionality for copying areas with trees and pasting them with multiple options. Here's how the complete system works:

## 🔄 Copy Process

### 1. **Area Detection & Tree Collection**
When you copy a drag area, the system:
```javascript
// Find trees within area bounds
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
- **Cutting Trees**: Trees with `plant_type === 'cutting'` and `mother_plant_id`
- **Related Trees**: Trees outside the area that have relationships with trees inside

### 3. **Clipboard Data Creation**
Creates comprehensive clipboard data:
```javascript
{
    id: "clipboard_timestamp",
    type: "dragArea",
    name: "Area Name",
    width: 5, height: 3,
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

## 📋 Paste Options Dialog

### **showPasteOptionsDialog()** Function
This is the main dialog that appears after copying, showing:

#### **Tree Breakdown Display**
- **Total Trees**: Complete count including related trees
- **Trees in Original Area**: Trees that were actually in the selected area
- **Related Trees**: Mother/cutting trees outside the area (included to preserve relationships)
- **Breeds**: List of unique breeds in the clipboard
- **Relationships**: Mother-cutting relationship information
- **Images**: Count of trees with images

#### **Paste Method Options**

1. **🎯 Click to Paste All Trees**
   - Pastes all trees (area + related) to maintain relationships
   - User clicks on grid to choose position
   - Preserves all plant relationships

2. **📍 Manual Position (All Trees)**
   - User enters specific row/column coordinates
   - Same as click-to-paste but with precise positioning
   - Includes validation for grid bounds

3. **📦 Area Trees Only** (if related trees exist)
   - Pastes only trees that were originally in the selected area
   - Excludes related trees outside the area
   - May break some plant relationships

4. **🔲 Area Boundary Only (No Trees)**
   - Creates just the area boundary without any trees
   - Useful for creating empty areas for future planting

## 🎯 Paste Execution

### **Click-to-Paste Mode**
```javascript
function enableClickToPaste() {
    window.clickToPasteMode = true;
    grid.classList.add('click-to-paste-mode');
    document.addEventListener('click', handlePasteClick, { capture: true });
}
```

### **Manual Paste Dialog**
Shows a form with:
- Starting row input (0 to currentRows-1)
- Starting column input (0 to currentCols-1)
- Area size validation warning
- Grid bounds checking

### **Tree Creation Process**
```javascript
async function executePasteAtPosition(targetRow, targetCol) {
    // Calculate offset from original to target position
    const offsetRow = targetRow - originalMinRow;
    const offsetCol = targetCol - originalMinCol;
    
    // Create each tree via API
    for (const tree of treesToCreate) {
        const newRow = parseInt(tree.internal_row) + offsetRow;
        const newCol = parseInt(tree.internal_col) + offsetCol;
        
        await fetch(`/api/dome/${domeId}/trees`, {
            method: 'POST',
            body: JSON.stringify({
                name: tree.name,
                breed: tree.breed,
                internal_row: newRow,
                internal_col: newCol,
                plant_type: tree.plant_type,
                mother_plant_id: tree.mother_plant_id,
                // ... other properties
            })
        });
    }
}
```

## 💾 Storage System

### **Multiple Storage Locations**
- `window.dragClipboard` - Global JavaScript variable
- `window.clipboardArea` - Compatibility variable
- `localStorage.globalDragClipboard` - Browser storage for persistence
- `window.copiedTreeData` - Single tree copy data

### **Cross-Page Persistence**
```javascript
// Load clipboard on page load
window.addEventListener('DOMContentLoaded', function() {
    const globalClipboard = localStorage.getItem('globalDragClipboard');
    if (globalClipboard) {
        window.dragClipboard = JSON.parse(globalClipboard);
        // Show paste button if data exists
    }
});
```

## 🔗 Relationship Preservation

### **Mother-Cutting Relationships**
The system preserves plant relationships by:
1. **Including related trees** even if outside the selected area
2. **Maintaining `mother_plant_id` references** in cutting trees
3. **Providing options** to paste with or without relationships
4. **Warning users** about potential relationship breaks

### **Relationship Analysis**
```javascript
// For each cutting in area, find its mother (if outside area)
cuttingTrees.forEach(cutting => {
    if (cutting.mother_plant_id) {
        const mother = trees.find(t => t.id === cutting.mother_plant_id);
        if (mother && !treesInArea.includes(mother)) {
            relatedTrees.push({...mother, isInOriginalArea: false});
        }
    }
});
```

## 🎨 Visual Feedback

### **Status Messages**
- Success/error notifications
- Progress updates during tree creation
- Validation warnings

### **Visual Indicators**
- Grid highlighting during paste mode
- Click-to-paste cursor changes
- Area boundary previews

### **Paste Button**
Shows clipboard status and tree count:
```javascript
pasteBtn.textContent = `📋 Paste ${clipboard.name} (${treeCount} trees)`;
```

## 🛠️ Error Handling

### **Validation Checks**
- **Grid bounds**: Ensures area fits within grid
- **Position validation**: Checks for valid row/column values
- **Overlap detection**: Optional checking for existing trees
- **API error handling**: Network and server error recovery

### **Graceful Degradation**
- Falls back to localStorage if global variables fail
- Provides manual input if click-to-paste fails
- Shows detailed error messages for debugging

## 📊 Usage Statistics

The system tracks and displays:
- Total trees copied
- Trees in original area vs. related trees
- Breed diversity
- Relationship completeness
- Success/failure rates during paste

## 🔧 Technical Features

### **Modern JavaScript**
- Uses async/await for API calls
- Proper event handling and cleanup
- Comprehensive error handling
- Modular function design

### **Performance Optimizations**
- Efficient tree filtering
- Minimal DOM manipulation
- Lazy loading of relationship data
- Optimized storage operations

## 🎯 Key Benefits

1. **🔗 Relationship Preservation**: Maintains mother-cutting connections
2. **🎛️ Flexible Pasting**: Multiple paste options for different needs
3. **🌐 Cross-Grid Support**: Copy from one grid and paste to another
4. **💾 Persistent Storage**: Clipboard survives page reloads
5. **🛡️ Error Recovery**: Robust error handling and user feedback
6. **📊 Detailed Information**: Comprehensive tree and relationship breakdown
7. **🎨 User-Friendly**: Clear visual feedback and intuitive interface

## 🚀 How to Use

1. **Create a drag area** by selecting trees with the drag selector
2. **Click the copy button** on the drag area
3. **Review the paste options dialog** showing tree breakdown
4. **Choose your paste method**:
   - Click-to-paste for interactive positioning
   - Manual position for precise coordinates
   - Area trees only to exclude related trees
   - Boundary only for empty areas
5. **Execute the paste** and see the results

The system provides a complete, professional-grade solution for copying and pasting tree areas while preserving complex plant relationships and providing flexible options for different use cases.