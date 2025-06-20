// ✅ CORRECTED PASTE BUTTON CLICK FIX
// This is the corrected version without syntax errors

(function() {
    console.log('🔧 Installing paste button click fix...');
    
    // ✅ FIXED handlePasteButtonClick function
    function fixedHandlePasteButtonClick() {
        console.log('🎯 Paste button clicked (FIXED VERSION)');
        
        // Check what's in clipboard
        let clipboard = window.dragClipboard || window.clipboardArea;
        
        if (!clipboard) {
            // Try loading from unified storage
            const UNIFIED_KEY = 'unifiedClipboard_dome_' + domeId;
            const BACKUP_KEY = 'clipboardBackup_dome_' + domeId;
            
            try {
                let stored = localStorage.getItem(UNIFIED_KEY);
                if (!stored) {
                    stored = localStorage.getItem(BACKUP_KEY);
                }
                
                if (stored) {
                    const data = JSON.parse(stored);
                    if (data && data.name && data.source_dome_id === domeId) {
                        console.log('📋 Loading clipboard from storage:', data.name);
                        window.dragClipboard = data;
                        window.clipboardArea = data;
                        clipboard = data;
                    } else {
                        console.warn('⚠️ No valid clipboard data found');
                        showStatus('No area in clipboard', 'warning');
                        return;
                    }
                } else {
                    console.warn('⚠️ No clipboard data in storage');
                    showStatus('No area in clipboard', 'warning');
                    return;
                }
            } catch (e) {
                console.error('❌ Error loading clipboard:', e);
                showStatus('Error loading clipboard', 'error');
                return;
            }
        }
        
        // ✅ ENHANCED: Process relationship data if available
        if (clipboard && clipboard.relationship_metadata) {
            console.log('🔗 Processing clipboard with relationship data');
            
            const relationshipData = clipboard.relationship_metadata;
            const motherCuttingPairs = relationshipData.mother_cutting_pairs || [];
            
            if (motherCuttingPairs.length > 0) {
                console.log('🌳 Processing mother trees with cutting relationships...');
                
                // Group cutting trees by their mother
                const motherGroups = {};
                motherCuttingPairs.forEach(pair => {
                    const motherId = pair.mother_original_id;
                    if (!motherGroups[motherId]) {
                        motherGroups[motherId] = {
                            mother: pair,
                            cuttings: []
                        };
                    }
                    if (pair.cutting_original_id) {
                        motherGroups[motherId].cuttings.push(pair);
                    }
                });
                
                // Store relationship data for paste operation
                clipboard.processedRelationships = {
                    motherGroups: motherGroups,
                    totalRelationships: motherCuttingPairs.length,
                    preservedRelationships: motherCuttingPairs.filter(p => p.relationship_preserved).length
                };
                
                console.log('✅ Relationship data processed and stored in clipboard');
            }
        }
        
        // ✅ CRITICAL: Show paste options dialog
        console.log('📋 Calling showPasteOptionsDialog...');
        if (typeof showPasteOptionsDialog === 'function') {
            showPasteOptionsDialog();
        } else {
            console.error('❌ showPasteOptionsDialog function not found');
            showStatus('Paste dialog not available', 'error');
        }
    }
    
    // ✅ ENSURE PASTE BUTTON HAS CORRECT ONCLICK HANDLER
    function ensurePasteButtonHandler() {
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn) {
            // Override the onclick handler
            pasteBtn.onclick = fixedHandlePasteButtonClick;
            console.log('✅ Paste button onclick handler set to fixed version');
            
            // Also add event listener for extra safety
            pasteBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                fixedHandlePasteButtonClick();
            });
            
            console.log('✅ Paste button click event listener added');
        } else {
            console.warn('⚠️ Paste button not found');
        }
    }
    
    // ✅ OVERRIDE THE GLOBAL FUNCTION
    window.handlePasteButtonClick = fixedHandlePasteButtonClick;
    
    // ✅ ENSURE BUTTON HANDLER IS SET
    setTimeout(ensurePasteButtonHandler, 500);
    setTimeout(ensurePasteButtonHandler, 2000); // Double check after page loads
    
    // ✅ ALSO ENSURE WHEN PASTE BUTTON IS UPDATED
    const originalUpdatePasteButtonDisplay = window.updatePasteButtonDisplay;
    if (originalUpdatePasteButtonDisplay) {
        window.updatePasteButtonDisplay = function() {
            // Call original function
            originalUpdatePasteButtonDisplay.apply(this, arguments);
            
            // Ensure handler is set after update
            setTimeout(ensurePasteButtonHandler, 100);
        };
    }
    
    console.log('✅ Paste button click fix installed');
    console.log('🎯 Paste button should now show the paste options dialog when clicked');
})();