// ✅ CORRECTED updatePasteButtonDisplay() FUNCTION
// Replace the existing function with this corrected version

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
            // ✅ FIXED: Use string concatenation instead of template literals to avoid syntax errors
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
            // �� FIXED: Use string concatenation instead of template literals
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
        // ✅ FIXED: Use string concatenation instead of template literals
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