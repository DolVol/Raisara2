// ✅ COMPLETE DOME ISOLATION AND PASTE BUTTON FIX
// Add this JavaScript code to your grid.html file

// ✅ 1. ADD updatePasteButtonDisplay() FUNCTION
function updatePasteButtonDisplay() {
    const pasteBtn = document.getElementById('pasteAreaBtn');
    if (!pasteBtn) return;

    // Check what's in clipboard (priority order)
    const dragClipboard = window.dragClipboard;
    const clipboardArea = window.clipboardArea;
    const copiedTreeData = window.copiedTreeData;

    console.log('🔄 Updating paste button display...');
    console.log('dragClipboard:', dragClipboard?.name);
    console.log('clipboardArea:', clipboardArea?.name);
    console.log('copiedTreeData:', copiedTreeData?.tree?.name);

    if (dragClipboard) {
        pasteBtn.style.display = 'block';
        
        if (dragClipboard.type === 'single_tree') {
            const treeName = dragClipboard.copied_tree_data?.tree?.name || dragClipboard.name || 'Tree';
            const relationshipCount = dragClipboard.copied_tree_data?.relationships?.total_cuttings || 0;
            pasteBtn.textContent = `📋 Paste "${treeName}"${relationshipCount > 0 ? ` (+${relationshipCount})` : ''}`;
        } else {
            const treeCount = dragClipboard.tree_count || dragClipboard.trees?.length || 0;
            pasteBtn.textContent = `📋 Paste ${dragClipboard.name || 'Area'} (${treeCount} trees)`;
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
            pasteBtn.textContent = `📋 Paste "${treeName}"${relationshipCount > 0 ? ` (+${relationshipCount})` : ''}`;
        } else {
            const treeCount = clipboardArea.tree_count || clipboardArea.trees?.length || 0;
            pasteBtn.textContent = `📋 Paste ${clipboardArea.name || 'Area'} (${treeCount} trees)`;
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
        pasteBtn.textContent = `📋 Paste "${treeName}"${relationshipCount > 0 ? ` (+${relationshipCount})` : ''}`;
        
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

// ✅ 2. ADD clearClipboardStorage() FUNCTION
function clearClipboardStorage() {
    try {
        console.log('🗑️ Clearing clipboard for dome', domeId);
        
        // Clear dome-specific clipboard first
        localStorage.removeItem(`domeClipboard_${domeId}`);
        
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

// ✅ 3. ADD CLIPBOARD PROPERTY WATCHERS
(function() {
    let _dragClipboard = window.dragClipboard || null;
    let _clipboardArea = window.clipboardArea || null;
    let _copiedTreeData = window.copiedTreeData || null;
    
    Object.defineProperty(window, 'dragClipboard', {
        get: function() { return _dragClipboard; },
        set: function(value) {
            _dragClipboard = value;
            console.log('📋 dragClipboard updated:', value?.name);
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

// ✅ 4. CALL UPDATE ON PAGE LOAD
setTimeout(function() {
    updatePasteButtonDisplay();
    console.log('✅ Initial paste button update completed');
}, 500);

console.log('✅ Complete dome isolation and paste button management loaded');