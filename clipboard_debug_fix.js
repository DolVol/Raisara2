// ✅ CLIPBOARD DEBUG AND FIX
// Add this to debug and fix the clipboard issue

// Debug function to check clipboard state
function debugClipboard() {
    console.log('=== CLIPBOARD DEBUG ===');
    console.log('window.dragClipboard:', window.dragClipboard);
    console.log('window.clipboardArea:', window.clipboardArea);
    console.log('window.copiedTreeData:', window.copiedTreeData);
    
    // Check localStorage
    const unifiedKey = 'unifiedClipboard_dome_' + domeId;
    const unifiedData = localStorage.getItem(unifiedKey);
    console.log('Unified clipboard key:', unifiedKey);
    console.log('Unified clipboard data:', unifiedData);
    
    // Check all possible localStorage keys
    const allKeys = [
        'globalDragClipboard', 'globalTreeClipboard', 'globalRegularClipboard',
        'copiedTreeData', 'clipboardArea', 'dragClipboard'
    ];
    
    allKeys.forEach(key => {
        const data = localStorage.getItem(key);
        if (data) {
            console.log('Found data in', key, ':', data.substring(0, 100) + '...');
        }
    });
    
    console.log('=== END CLIPBOARD DEBUG ===');
}

// Fixed updatePasteButtonDisplay that properly checks for data
function updatePasteButtonDisplayFixed() {
    const pasteBtn = document.getElementById('pasteAreaBtn');
    if (!pasteBtn) return;

    console.log('🔄 Updating paste button display (FIXED VERSION)...');
    
    // Check what's in clipboard (priority order)
    const dragClipboard = window.dragClipboard;
    const clipboardArea = window.clipboardArea;
    const copiedTreeData = window.copiedTreeData;
    
    console.log('Checking clipboard data:');
    console.log('- dragClipboard:', dragClipboard?.name || 'null');
    console.log('- clipboardArea:', clipboardArea?.name || 'null');
    console.log('- copiedTreeData:', copiedTreeData?.tree?.name || 'null');

    // ✅ STRICT CHECK: Only show button if there's actual data
    if (dragClipboard && dragClipboard.name) {
        pasteBtn.style.display = 'block';
        
        if (dragClipboard.type === 'single_tree') {
            const treeName = dragClipboard.copied_tree_data?.tree?.name || dragClipboard.name || 'Tree';
            const relationshipCount = dragClipboard.copied_tree_data?.relationships?.total_cuttings || 0;
            if (relationshipCount > 0) {
                pasteBtn.textContent = '📋 Paste "' + treeName + '" (+' + relationshipCount + ')';
            } else {
                pasteBtn.textContent = '📋 Paste "' + treeName + '"';
            }
        } else {
            const treeCount = dragClipboard.tree_count || dragClipboard.trees?.length || 0;
            pasteBtn.textContent = '📋 Paste ' + (dragClipboard.name || 'Area') + ' (' + treeCount + ' trees)';
        }
        
        if (dragClipboard.source_dome_id && dragClipboard.source_dome_id !== domeId) {
            pasteBtn.textContent += ' [Cross-Dome]';
            pasteBtn.classList.add('paste-btn-cross-dome');
        } else {
            pasteBtn.classList.remove('paste-btn-cross-dome');
        }
        
        console.log('✅ Paste button shown with:', pasteBtn.textContent);
        
    } else if (clipboardArea && clipboardArea.name) {
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
        
        if (clipboardArea.source_dome_id && clipboardArea.source_dome_id !== domeId) {
            pasteBtn.textContent += ' [Cross-Dome]';
            pasteBtn.classList.add('paste-btn-cross-dome');
        } else {
            pasteBtn.classList.remove('paste-btn-cross-dome');
        }
        
        console.log('✅ Paste button shown with:', pasteBtn.textContent);
        
    } else if (copiedTreeData && copiedTreeData.tree && copiedTreeData.tree.name) {
        pasteBtn.style.display = 'block';
        const treeName = copiedTreeData.tree.name;
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
        
        console.log('✅ Paste button shown with:', pasteBtn.textContent);
    } else {
        // ✅ NO DATA: Hide the button
        pasteBtn.style.display = 'none';
        pasteBtn.textContent = '📋 Paste Area';
        console.log('❌ No clipboard data found, hiding paste button');
    }
}

// Fixed unified clipboard system that doesn't clear existing valid data
function fixedUnifiedClipboardSystem() {
    console.log('🔧 Installing FIXED Unified Clipboard System...');
    
    const UNIFIED_KEY = 'unifiedClipboard_dome_' + domeId;
    
    // ✅ DON'T CLEAR DATA IMMEDIATELY - Check if there's valid data first
    function loadExistingClipboard() {
        // Check unified storage first
        try {
            const stored = localStorage.getItem(UNIFIED_KEY);
            if (stored) {
                const data = JSON.parse(stored);
                if (data.source_dome_id === domeId && data.name) {
                    console.log('📋 Found valid unified clipboard:', data.name);
                    window.dragClipboard = data;
                    window.clipboardArea = data;
                    return data;
                }
            }
        } catch (e) {
            console.warn('⚠️ Error loading unified clipboard:', e);
        }
        
        // Check other storage locations for valid data
        const otherKeys = ['globalDragClipboard', 'globalTreeClipboard', 'copiedTreeData'];
        for (const key of otherKeys) {
            try {
                const stored = localStorage.getItem(key);
                if (stored) {
                    const data = JSON.parse(stored);
                    if (data && data.name) {
                        console.log('📋 Found valid clipboard in', key, ':', data.name);
                        // Migrate to unified storage
                        const unifiedData = {
                            ...data,
                            source_dome_id: domeId,
                            copied_at: new Date().toISOString(),
                            unified_version: '1.0'
                        };
                        localStorage.setItem(UNIFIED_KEY, JSON.stringify(unifiedData));
                        window.dragClipboard = unifiedData;
                        window.clipboardArea = unifiedData;
                        return unifiedData;
                    }
                }
            } catch (e) {
                // Continue checking other keys
            }
        }
        
        console.log('📋 No valid clipboard data found');
        return null;
    }
    
    // Load existing data
    const existingData = loadExistingClipboard();
    
    // Override the updatePasteButtonDisplay function
    window.updatePasteButtonDisplay = updatePasteButtonDisplayFixed;
    
    // Update the display
    updatePasteButtonDisplayFixed();
    
    console.log('✅ FIXED Unified Clipboard System installed');
    if (existingData) {
        console.log('📋 Clipboard data preserved:', existingData.name);
    }
}

// Install the fixed system
fixedUnifiedClipboardSystem();

// Make debug function available globally
window.debugClipboard = debugClipboard;

console.log('✅ Clipboard debug and fix loaded. Use debugClipboard() to check state.');