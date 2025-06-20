// ✅ COMPLETE FIX FOR CLIPBOARD ISSUES
// Add this to your grid.html file to fix both the display errors and the "Copied Tree: 333" persistence

// ✅ 1. CORRECTED updatePasteButtonDisplay() FUNCTION
function updatePasteButtonDisplay() {
    const pasteBtn = document.getElementById('pasteAreaBtn');
    if (!pasteBtn) return;

    // Check what's in clipboard (priority order)
    const dragClipboard = window.dragClipboard;
    const clipboardArea = window.clipboardArea;
    const copiedTreeData = window.copiedTreeData;

    console.log('🔄 Updating paste button display...');

    if (dragClipboard) {
        pasteBtn.style.display = 'block';
        
        if (dragClipboard.type === 'single_tree') {
            const treeName = dragClipboard.copied_tree_data?.tree?.name || dragClipboard.name || 'Tree';
            const relationshipCount = dragClipboard.copied_tree_data?.relationships?.total_cuttings || 0;
            // ✅ FIXED: Use string concatenation to avoid template literal errors
            if (relationshipCount > 0) {
                pasteBtn.textContent = '📋 Paste "' + treeName + '" (+' + relationshipCount + ')';
            } else {
                pasteBtn.textContent = '📋 Paste "' + treeName + '"';
            }
        } else {
            const treeCount = dragClipboard.tree_count || dragClipboard.trees?.length || 0;
            pasteBtn.textContent = '📋 Paste ' + (dragClipboard.name || 'Area') + ' (' + treeCount + ' trees)';
        }
        
        // Add cross-dome indicator if from different dome
        if (dragClipboard.source_dome_id && dragClipboard.source_dome_id !== domeId) {
            pasteBtn.textContent += ' [Cross-Dome]';
            pasteBtn.classList.add('paste-btn-cross-dome');
        } else {
            pasteBtn.classList.remove('paste-btn-cross-dome');
        }
        
    } else if (clipboardArea) {
        pasteBtn.style.display = 'block';
        
        if (clipboardArea.type === 'single_tree') {
            const treeName = clipboardArea.copied_tree_data?.tree?.name || clipboardArea.name || 'Tree';
            const relationshipCount = clipboardArea.copied_tree_data?.relationships?.total_cuttings || 0;
            if (relationshipCount > 0) {
                pasteBtn.textContent = '📋 Paste "' + treeName + '" (+' + relationshipCount + ')';
            } else {
                pasteBtn.textContent = '📋 Paste "' + treeName + '"';
            }
        } else {
            const treeCount = clipboardArea.tree_count || clipboardArea.trees?.length || 0;
            pasteBtn.textContent = '📋 Paste ' + (clipboardArea.name || 'Area') + ' (' + treeCount + ' trees)';
        }
        
        // Add cross-dome indicator if from different dome
        if (clipboardArea.source_dome_id && clipboardArea.source_dome_id !== domeId) {
            pasteBtn.textContent += ' [Cross-Dome]';
            pasteBtn.classList.add('paste-btn-cross-dome');
        } else {
            pasteBtn.classList.remove('paste-btn-cross-dome');
        }
        
    } else if (copiedTreeData) {
        pasteBtn.style.display = 'block';
        const treeName = copiedTreeData.tree?.name || 'Tree';
        const relationshipCount = copiedTreeData.relationships?.total_cuttings || 0;
        if (relationshipCount > 0) {
            pasteBtn.textContent = '📋 Paste "' + treeName + '" (+' + relationshipCount + ')';
        } else {
            pasteBtn.textContent = '📋 Paste "' + treeName + '"';
        }
        
        if (copiedTreeData.source_dome_id && copiedTreeData.source_dome_id !== domeId) {
            pasteBtn.textContent += ' [Cross-Dome]';
            pasteBtn.classList.add('paste-btn-cross-dome');
        } else {
            pasteBtn.classList.remove('paste-btn-cross-dome');
        }
    } else {
        pasteBtn.style.display = 'none';
        pasteBtn.textContent = '📋 Paste Area';
    }
    
    console.log('✅ Paste button updated:', pasteBtn.textContent);
}

// ✅ 2. CLEAR CLIPBOARD FUNCTION
function clearClipboardStorage() {
    try {
        console.log('🗑️ Clearing clipboard for dome', domeId);
        
        // Clear dome-specific clipboard first
        localStorage.removeItem('domeClipboard_' + domeId);
        
        // Clear global clipboard only if it's from this dome
        const globalDrag = localStorage.getItem('globalDragClipboard');
        const globalTree = localStorage.getItem('globalTreeClipboard');
        
        if (globalDrag) {
            try {
                const data = JSON.parse(globalDrag);
                if (!data.source_dome_id || data.source_dome_id === domeId) {
                    localStorage.removeItem('globalDragClipboard');
                    localStorage.removeItem('globalDragClipboardTimestamp');
                    console.log('🗑️ Cleared global drag clipboard');
                }
            } catch (e) {
                localStorage.removeItem('globalDragClipboard');
                console.log('🗑️ Cleared corrupted global drag clipboard');
            }
        }
        
        if (globalTree) {
            try {
                const data = JSON.parse(globalTree);
                if (!data.source_dome_id || data.source_dome_id === domeId) {
                    localStorage.removeItem('globalTreeClipboard');
                    console.log('🗑️ Cleared global tree clipboard');
                }
            } catch (e) {
                localStorage.removeItem('globalTreeClipboard');
                console.log('🗑️ Cleared corrupted global tree clipboard');
            }
        }
        
        // Clear in-memory clipboard
        window.dragClipboard = null;
        window.clipboardArea = null;
        window.copiedTreeData = null;
        
        // Update paste button
        updatePasteButtonDisplay();
        
        console.log('✅ Clipboard cleared successfully');
        showStatus('Clipboard cleared', 'info');
    } catch (e) {
        console.warn('⚠️ Error clearing clipboard:', e);
    }
}

// ✅ 3. CLIPBOARD PROPERTY WATCHERS
(function() {
    let _dragClipboard = window.dragClipboard || null;
    let _clipboardArea = window.clipboardArea || null;
    let _copiedTreeData = window.copiedTreeData || null;
    
    Object.defineProperty(window, 'dragClipboard', {
        get: function() { return _dragClipboard; },
        set: function(value) {
            _dragClipboard = value;
            console.log('���� dragClipboard updated:', value?.name);
            setTimeout(updatePasteButtonDisplay, 100);
        }
    });
    
    Object.defineProperty(window, 'clipboardArea', {
        get: function() { return _clipboardArea; },
        set: function(value) {
            _clipboardArea = value;
            console.log('📋 clipboardArea updated:', value?.name);
            setTimeout(updatePasteButtonDisplay, 100);
        }
    });
    
    Object.defineProperty(window, 'copiedTreeData', {
        get: function() { return _copiedTreeData; },
        set: function(value) {
            _copiedTreeData = value;
            console.log('📋 copiedTreeData updated:', value?.tree?.name);
            setTimeout(updatePasteButtonDisplay, 100);
        }
    });
    
    console.log('✅ Clipboard property watchers installed');
})();

// ✅ 4. OVERRIDE CLIPBOARD STORAGE TO FIX "Copied Tree: 333" ISSUE
(function() {
    // Override the storeClipboardData function to add proper dome isolation
    const originalStoreClipboardData = window.storeClipboardData;
    
    window.storeClipboardData = function(clipboardData, source) {
        console.log('🔧 OVERRIDE: storeClipboardData called with:', clipboardData?.name, 'source:', source);
        
        // ✅ ADD DOME ID AND TIMESTAMP TO CLIPBOARD DATA
        const enhancedClipboardData = {
            ...clipboardData,
            source_dome_id: domeId,
            copied_at: new Date().toISOString(),
            clipboard_source: source
        };
        
        console.log('💾 Storing clipboard data with dome isolation:', enhancedClipboardData.name, 'for dome', domeId);
        
        // Store in multiple locations for compatibility
        window.dragClipboard = enhancedClipboardData;
        window.clipboardArea = enhancedClipboardData;
        
        // Save to localStorage with dome isolation
        try {
            // ✅ PRIORITY 1: Store dome-specific clipboard (prevents cross-contamination)
            localStorage.setItem('domeClipboard_' + domeId, JSON.stringify(enhancedClipboardData));
            console.log('✅ Saved dome-specific clipboard:', 'domeClipboard_' + domeId);
            
            // ✅ PRIORITY 2: Store global clipboard for cross-dome pasting (when intended)
            localStorage.setItem('globalDragClipboard', JSON.stringify(enhancedClipboardData));
            localStorage.setItem('globalClipboardTimestamp', Date.now().toString());
            console.log('✅ Saved global clipboard with dome ID:', enhancedClipboardData.source_dome_id);
            
            console.log('✅ Clipboard saved successfully with dome isolation');
            
        } catch (e) {
            console.warn('⚠️ Could not save clipboard to localStorage:', e);
        }
        
        // Update paste button immediately
        setTimeout(updatePasteButtonDisplay, 100);
    };
    
    console.log('✅ storeClipboardData function overridden with dome isolation');
})();

// ✅ 5. ALSO OVERRIDE DRAG SELECTOR METHODS
(function() {
    // Wait for dragSelector to be available and override its methods
    setTimeout(function() {
        if (typeof dragSelector !== 'undefined' && dragSelector && typeof dragSelector.storeClipboardData === 'function') {
            const originalMethod = dragSelector.storeClipboardData.bind(dragSelector);
            
            dragSelector.storeClipboardData = function(clipboardData, source) {
                console.log('🔧 OVERRIDE: dragSelector.storeClipboardData called with:', clipboardData?.name);
                
                // Add dome isolation
                const enhancedClipboardData = {
                    ...clipboardData,
                    source_dome_id: domeId,
                    copied_at: new Date().toISOString(),
                    clipboard_source: source
                };
                
                // Call the global override instead
                if (typeof window.storeClipboardData === 'function') {
                    window.storeClipboardData(enhancedClipboardData, source);
                } else {
                    // Fallback to original method
                    originalMethod(enhancedClipboardData, source);
                }
            };
            
            console.log('✅ dragSelector.storeClipboardData overridden with dome isolation');
        } else {
            console.log('⚠️ dragSelector not found, will try again later');
        }
    }, 1000);
})();

// ✅ 6. CALL UPDATE ON PAGE LOAD
setTimeout(function() {
    updatePasteButtonDisplay();
    console.log('✅ Initial paste button update completed');
}, 500);

console.log('✅ COMPLETE CLIPBOARD FIX APPLIED - This should resolve all issues');