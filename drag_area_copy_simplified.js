// ✅ SIMPLIFIED: Drag Area Copy System
// This file contains the core drag area copying functionality

class DragAreaCopySystem {
    constructor() {
        this.clipboard = null;
        this.initializeClipboard();
    }

    // Initialize clipboard from localStorage
    initializeClipboard() {
        try {
            const stored = localStorage.getItem('globalDragClipboard');
            if (stored) {
                this.clipboard = JSON.parse(stored);
                console.log('📋 Loaded clipboard from storage:', this.clipboard);
                this.showPasteButton();
            }
        } catch (e) {
            console.warn('⚠️ Could not load clipboard:', e);
        }
    }

    // Copy drag area to clipboard
    async copyDragArea(areaId) {
        try {
            console.log(`📋 Copying drag area ${areaId}`);
            
            // Find the area
            const area = dragAreas.find(a => a.id === areaId);
            if (!area) {
                throw new Error('Drag area not found');
            }

            // Find trees in the area bounds
            const treesInArea = this.findTreesInArea(area);
            console.log(`🔍 Found ${treesInArea.length} trees in area`);

            // Analyze relationships
            const relationshipData = this.analyzeRelationships(treesInArea);
            
            // Create clipboard data
            const clipboardData = this.createClipboardData(area, treesInArea, relationshipData);
            
            // Store clipboard data
            this.storeClipboard(clipboardData);
            
            // Show success message
            const message = `Area "${area.name}" copied (${treesInArea.length} trees)`;
            showStatus(message, 'success');
            
            // Show paste options
            setTimeout(() => this.showPasteOptions(), 500);
            
        } catch (error) {
            console.error('❌ Error copying area:', error);
            showStatus('Error copying area: ' + error.message, 'error');
        }
    }

    // Find trees within area bounds
    findTreesInArea(area) {
        return trees.filter(tree => {
            if (!tree || tree.internal_row === undefined || tree.internal_col === undefined) {
                return false;
            }
            
            const treeRow = parseInt(tree.internal_row);
            const treeCol = parseInt(tree.internal_col);
            const minRow = parseInt(area.minRow);
            const maxRow = parseInt(area.maxRow);
            const minCol = parseInt(area.minCol);
            const maxCol = parseInt(area.maxCol);
            
            return treeRow >= minRow && treeRow <= maxRow && 
                   treeCol >= minCol && treeCol <= maxCol;
        });
    }

    // Analyze tree relationships
    analyzeRelationships(treesInArea) {
        const motherTrees = treesInArea.filter(t => t.plant_type === 'mother');
        const cuttingTrees = treesInArea.filter(t => t.plant_type === 'cutting');
        
        // Find related trees outside the area
        const relatedTrees = [];
        
        // For each cutting in area, find its mother (if outside area)
        cuttingTrees.forEach(cutting => {
            if (cutting.mother_plant_id) {
                const mother = trees.find(t => t.id === cutting.mother_plant_id);
                if (mother && !treesInArea.includes(mother)) {
                    relatedTrees.push({...mother, isInOriginalArea: false});
                }
            }
        });
        
        // For each mother in area, find its cuttings (if outside area)
        motherTrees.forEach(mother => {
            const cuttings = trees.filter(t => t.mother_plant_id === mother.id);
            cuttings.forEach(cutting => {
                if (!treesInArea.includes(cutting)) {
                    relatedTrees.push({...cutting, isInOriginalArea: false});
                }
            });
        });

        return {
            motherTrees: motherTrees.length,
            cuttingTrees: cuttingTrees.length,
            relatedTrees: relatedTrees,
            totalRelationships: motherTrees.length + cuttingTrees.length
        };
    }

    // Create clipboard data structure
    createClipboardData(area, treesInArea, relationshipData) {
        // Mark trees as being in original area
        const markedTrees = treesInArea.map(tree => ({
            ...tree,
            isInOriginalArea: true
        }));

        // Combine with related trees
        const allTrees = [...markedTrees, ...relationshipData.relatedTrees];

        return {
            id: `clipboard_${Date.now()}`,
            type: 'dragArea',
            name: area.name,
            width: area.width || (area.maxCol - area.minCol + 1),
            height: area.height || (area.maxRow - area.minRow + 1),
            minRow: area.minRow,
            maxRow: area.maxRow,
            minCol: area.minCol,
            maxCol: area.maxCol,
            color: area.color,
            
            // Tree data
            trees: allTrees,
            trees_data: allTrees,
            tree_count: allTrees.length,
            tree_ids: allTrees.map(t => t.id),
            
            // Summary information
            summary: {
                total_trees: allTrees.length,
                trees_in_original_area: treesInArea.length,
                related_trees_outside_area: relationshipData.relatedTrees.length,
                plant_relationships: {
                    mother_trees: relationshipData.motherTrees,
                    cutting_trees: relationshipData.cuttingTrees,
                    complete_relationships: relationshipData.totalRelationships
                }
            },
            
            // Metadata
            source_dome_id: domeId,
            copied_at: new Date().toISOString(),
            clipboard_source: 'drag_area_copy'
        };
    }

    // Store clipboard data
    storeClipboard(clipboardData) {
        this.clipboard = clipboardData;
        
        // Store globally
        window.dragClipboard = clipboardData;
        window.clipboardArea = clipboardData;
        
        // Store in localStorage
        try {
            localStorage.setItem('globalDragClipboard', JSON.stringify(clipboardData));
            console.log('✅ Clipboard data stored');
        } catch (e) {
            console.warn('⚠️ Could not save to localStorage:', e);
        }
        
        this.showPasteButton();
    }

    // Show paste button
    showPasteButton() {
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn && this.clipboard) {
            pasteBtn.style.display = 'block';
            const treeCount = this.clipboard.tree_count || 0;
            pasteBtn.textContent = `📋 Paste ${this.clipboard.name} (${treeCount} trees)`;
        }
    }

    // Show paste options dialog
    showPasteOptions() {
        if (!this.clipboard) {
            showStatus('No area in clipboard', 'warning');
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'paste-options-modal';
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            " onclick="this.remove();">
                <div style="
                    background: white;
                    border-radius: 12px;
                    padding: 25px;
                    max-width: 500px;
                    width: 90%;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                " onclick="event.stopPropagation();">
                    <h5 style="margin: 0 0 20px 0; color: #9c27b0;">📋 Paste Area</h5>
                    
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                        <div><strong>Area:</strong> ${this.clipboard.name}</div>
                        <div><strong>Size:</strong> ${this.clipboard.width}×${this.clipboard.height}</div>
                        <div><strong>Total Trees:</strong> ${this.clipboard.tree_count}</div>
                        <div><strong>Trees in Area:</strong> ${this.clipboard.summary.trees_in_original_area}</div>
                        ${this.clipboard.summary.related_trees_outside_area > 0 ? 
                            `<div><strong>Related Trees:</strong> ${this.clipboard.summary.related_trees_outside_area}</div>` : ''}
                    </div>
                    
                    <div style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px;">
                        <button onclick="dragAreaCopySystem.enableClickToPaste(); this.closest('.paste-options-modal').remove();" 
                                style="padding: 12px 20px; background: #007bff; color: white; border: none; border-radius: 6px; cursor: pointer;">
                            🎯 Click to Paste All Trees
                        </button>
                        
                        <button onclick="dragAreaCopySystem.showManualPasteDialog(); this.closest('.paste-options-modal').remove();" 
                                style="padding: 12px 20px; background: #28a745; color: white; border: none; border-radius: 6px; cursor: pointer;">
                            📍 Manual Position
                        </button>
                        
                        ${this.clipboard.summary.related_trees_outside_area > 0 ? `
                            <button onclick="dragAreaCopySystem.pasteAreaTreesOnly(); this.closest('.paste-options-modal').remove();" 
                                    style="padding: 12px 20px; background: #17a2b8; color: white; border: none; border-radius: 6px; cursor: pointer;">
                                📦 Area Trees Only
                            </button>
                        ` : ''}
                    </div>
                    
                    <div style="display: flex; justify-content: space-between;">
                        <button onclick="dragAreaCopySystem.clearClipboard(); this.closest('.paste-options-modal').remove();" 
                                style="padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            🗑️ Clear
                        </button>
                        <button onclick="this.closest('.paste-options-modal').remove();" 
                                style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            ❌ Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }

    // Enable click-to-paste mode
    enableClickToPaste() {
        if (!this.clipboard) {
            showStatus('No area in clipboard', 'error');
            return;
        }

        // Enable click mode
        window.clickToPasteMode = true;
        
        // Add visual indicator
        const grid = document.getElementById('treeGrid');
        if (grid) {
            grid.classList.add('click-to-paste-mode');
        }
        
        // Show instructions
        showStatus('Click on an empty area to paste', 'info', 5000);
        
        // Add click handler
        document.addEventListener('click', this.handlePasteClick.bind(this), { once: false });
    }

    // Handle paste click
    handlePasteClick(event) {
        if (!window.clickToPasteMode || !this.clipboard) return;

        const cell = event.target.closest('.grid-cell');
        if (!cell || !cell.dataset.row || !cell.dataset.col) return;

        const targetRow = parseInt(cell.dataset.row);
        const targetCol = parseInt(cell.dataset.col);

        // Check if position is valid
        if (this.canPasteAt(targetRow, targetCol)) {
            this.executePaste(targetRow, targetCol);
        } else {
            showStatus('Cannot paste here - area would extend outside grid or overlap existing trees', 'error');
        }
    }

    // Check if can paste at position
    canPasteAt(targetRow, targetCol) {
        const endRow = targetRow + this.clipboard.height - 1;
        const endCol = targetCol + this.clipboard.width - 1;

        // Check grid bounds
        if (endRow >= currentRows || endCol >= currentCols) {
            return false;
        }

        // Check for overlapping trees (optional - you might want to allow overwriting)
        for (let row = targetRow; row <= endRow; row++) {
            for (let col = targetCol; col <= endCol; col++) {
                const existingTree = trees.find(t => 
                    parseInt(t.internal_row) === row && 
                    parseInt(t.internal_col) === col
                );
                if (existingTree) {
                    return false; // Position occupied
                }
            }
        }

        return true;
    }

    // Execute paste operation
    async executePaste(targetRow, targetCol) {
        try {
            showStatus('Pasting trees...', 'info');
            
            let createdCount = 0;
            let failedCount = 0;

            // Calculate offset from original position
            const offsetRow = targetRow - this.clipboard.minRow;
            const offsetCol = targetCol - this.clipboard.minCol;

            // Create trees
            for (const tree of this.clipboard.trees) {
                if (!tree.isInOriginalArea) continue; // Skip related trees for now

                const newRow = parseInt(tree.internal_row) + offsetRow;
                const newCol = parseInt(tree.internal_col) + offsetCol;

                try {
                    const response = await fetch(`/api/dome/${domeId}/trees`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: tree.name,
                            breed: tree.breed || '',
                            internal_row: newRow,
                            internal_col: newCol,
                            plant_type: tree.plant_type || 'mother',
                            mother_plant_id: tree.mother_plant_id || null,
                            info: tree.info || ''
                        })
                    });

                    if (response.ok) {
                        createdCount++;
                    } else {
                        failedCount++;
                    }
                } catch (error) {
                    failedCount++;
                    console.error('Error creating tree:', error);
                }
            }

            // Disable click mode
            this.disableClickToPaste();

            // Show results
            if (createdCount > 0) {
                showStatus(`Successfully pasted ${createdCount} trees!`, 'success');
                // Refresh the grid
                setTimeout(() => window.location.reload(), 1000);
            } else {
                showStatus('Failed to paste any trees', 'error');
            }

        } catch (error) {
            console.error('Error pasting:', error);
            showStatus('Error pasting trees', 'error');
            this.disableClickToPaste();
        }
    }

    // Disable click-to-paste mode
    disableClickToPaste() {
        window.clickToPasteMode = false;
        
        const grid = document.getElementById('treeGrid');
        if (grid) {
            grid.classList.remove('click-to-paste-mode');
        }
        
        document.removeEventListener('click', this.handlePasteClick);
    }

    // Show manual paste dialog
    showManualPasteDialog() {
        if (!this.clipboard) return;

        const modal = document.createElement('div');
        modal.innerHTML = `
            <div style="
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            " onclick="this.remove();">
                <div style="
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    max-width: 400px;
                    width: 90%;
                " onclick="event.stopPropagation();">
                    <h5>📍 Manual Paste Position</h5>
                    
                    <div style="margin: 15px 0;">
                        <label>Row: <input type="number" id="manualRow" min="0" max="${currentRows-1}" value="0"></label>
                    </div>
                    <div style="margin: 15px 0;">
                        <label>Column: <input type="number" id="manualCol" min="0" max="${currentCols-1}" value="0"></label>
                    </div>
                    
                    <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                        <button onclick="this.remove()" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px;">
                            Cancel
                        </button>
                        <button onclick="dragAreaCopySystem.executeManualPaste(); this.remove();" style="padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 4px;">
                            Paste
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }

    // Execute manual paste
    executeManualPaste() {
        const row = parseInt(document.getElementById('manualRow').value);
        const col = parseInt(document.getElementById('manualCol').value);
        
        if (this.canPasteAt(row, col)) {
            this.executePaste(row, col);
        } else {
            showStatus('Invalid paste position', 'error');
        }
    }

    // Paste only trees that were in the original area
    pasteAreaTreesOnly() {
        if (!this.clipboard) return;

        // Create modified clipboard with only area trees
        const areaTreesOnly = {
            ...this.clipboard,
            trees: this.clipboard.trees.filter(t => t.isInOriginalArea !== false),
            tree_count: this.clipboard.trees.filter(t => t.isInOriginalArea !== false).length
        };

        const originalClipboard = this.clipboard;
        this.clipboard = areaTreesOnly;
        
        this.enableClickToPaste();
        
        // Restore original clipboard after paste
        setTimeout(() => {
            this.clipboard = originalClipboard;
        }, 100);
    }

    // Clear clipboard
    clearClipboard() {
        this.clipboard = null;
        window.dragClipboard = null;
        window.clipboardArea = null;
        
        try {
            localStorage.removeItem('globalDragClipboard');
        } catch (e) {
            console.warn('Could not clear localStorage:', e);
        }
        
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn) {
            pasteBtn.style.display = 'none';
        }
        
        showStatus('Clipboard cleared', 'info');
    }
}

// Initialize the system
const dragAreaCopySystem = new DragAreaCopySystem();

// Make it globally available
window.dragAreaCopySystem = dragAreaCopySystem;

// Helper function for the existing drag selector
if (typeof DragSelector !== 'undefined') {
    DragSelector.prototype.copyDragArea = function(areaId) {
        dragAreaCopySystem.copyDragArea(areaId);
    };
}

console.log('✅ Drag Area Copy System initialized');