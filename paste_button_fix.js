// ✅ PASTE BUTTON PERSISTENCE FIX
// This ensures the paste button shows correctly when navigating between pages

(function() {
    console.log('🔧 Installing paste button persistence fix...');
    
    // ✅ ENHANCED CLIPBOARD PERSISTENCE
    function ensureClipboardPersistence() {
        const UNIFIED_KEY = 'unifiedClipboard_dome_' + domeId;
        const BACKUP_KEY = 'clipboardBackup_dome_' + domeId;
        
        // Save current clipboard to backup before navigation
        function saveClipboardBackup() {
            const currentClipboard = window.dragClipboard || window.clipboardArea;
            if (currentClipboard && currentClipboard.name) {
                try {
                    localStorage.setItem(BACKUP_KEY, JSON.stringify(currentClipboard));
                    localStorage.setItem(UNIFIED_KEY, JSON.stringify(currentClipboard));
                    console.log('💾 Clipboard backed up before navigation:', currentClipboard.name);
                } catch (e) {
                    console.warn('⚠️ Failed to backup clipboard:', e);
                }
            }
        }
        
        // Restore clipboard from backup after navigation
        function restoreClipboardFromBackup() {
            try {
                // Try unified storage first
                let stored = localStorage.getItem(UNIFIED_KEY);
                if (!stored) {
                    // Fallback to backup
                    stored = localStorage.getItem(BACKUP_KEY);
                }
                
                if (stored) {
                    const data = JSON.parse(stored);
                    if (data && data.name && data.source_dome_id === domeId) {
                        console.log('📋 Restoring clipboard from backup:', data.name);
                        window.dragClipboard = data;
                        window.clipboardArea = data;
                        
                        // Update paste button
                        if (typeof updatePasteButtonDisplay === 'function') {
                            setTimeout(updatePasteButtonDisplay, 100);
                        }
                        
                        return true;
                    }
                }
            } catch (e) {
                console.warn('⚠️ Failed to restore clipboard:', e);
            }
            return false;
        }
        
        // Override navigation functions to save clipboard
        const originalOpenDomeInfo = window.openDomeInfo;
        if (originalOpenDomeInfo) {
            window.openDomeInfo = function() {
                console.log('🔄 openDomeInfo called - saving clipboard...');
                saveClipboardBackup();
                return originalOpenDomeInfo.apply(this, arguments);
            };
        }
        
        const originalGoBack = window.goBack;
        if (originalGoBack) {
            window.goBack = function() {
                console.log('🔄 goBack called - saving clipboard...');
                saveClipboardBackup();
                return originalGoBack.apply(this, arguments);
            };
        }
        
        // Restore clipboard on page load
        setTimeout(function() {
            const restored = restoreClipboardFromBackup();
            if (restored) {
                console.log('✅ Clipboard restored successfully');
            } else {
                console.log('📋 No clipboard to restore');
            }
        }, 1000);
        
        return { saveClipboardBackup, restoreClipboardFromBackup };
    }
    
    // ✅ ENHANCED PASTE BUTTON DISPLAY
    function enhancedPasteButtonDisplay() {
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (!pasteBtn) {
            console.warn('⚠️ Paste button not found');
            return;
        }

        console.log('🔄 Enhanced paste button display check...');
        
        // Check all possible clipboard sources
        const dragClipboard = window.dragClipboard;
        const clipboardArea = window.clipboardArea;
        const copiedTreeData = window.copiedTreeData;
        
        // Also check localStorage directly
        const UNIFIED_KEY = 'unifiedClipboard_dome_' + domeId;
        const BACKUP_KEY = 'clipboardBackup_dome_' + domeId;
        
        let clipboardData = null;
        
        // Priority 1: In-memory clipboard
        if (dragClipboard && dragClipboard.name) {
            clipboardData = dragClipboard;
            console.log('📋 Found dragClipboard:', clipboardData.name);
        } else if (clipboardArea && clipboardArea.name) {
            clipboardData = clipboardArea;
            console.log('📋 Found clipboardArea:', clipboardData.name);
        } else if (copiedTreeData && copiedTreeData.tree && copiedTreeData.tree.name) {
            clipboardData = copiedTreeData;
            console.log('📋 Found copiedTreeData:', clipboardData.tree.name);
        } else {
            // Priority 2: Check localStorage
            try {
                let stored = localStorage.getItem(UNIFIED_KEY);
                if (!stored) {
                    stored = localStorage.getItem(BACKUP_KEY);
                }
                
                if (stored) {
                    const data = JSON.parse(stored);
                    if (data && data.name && data.source_dome_id === domeId) {
                        clipboardData = data;
                        console.log('📋 Found stored clipboard:', clipboardData.name);
                        
                        // Restore to memory
                        window.dragClipboard = data;
                        window.clipboardArea = data;
                    }
                }
            } catch (e) {
                console.warn('⚠️ Error checking stored clipboard:', e);
            }
        }
        
        // Update paste button based on found data
        if (clipboardData && clipboardData.name) {
            pasteBtn.style.display = 'block';
            
            if (clipboardData.type === 'single_tree') {
                const treeName = clipboardData.copied_tree_data?.tree?.name || clipboardData.name || 'Tree';
                const relationshipCount = clipboardData.copied_tree_data?.relationships?.total_cuttings || 0;
                if (relationshipCount > 0) {
                    pasteBtn.textContent = '📋 Paste "' + treeName + '" (+' + relationshipCount + ')';
                } else {
                    pasteBtn.textContent = '📋 Paste "' + treeName + '"';
                }
            } else {
                const treeCount = clipboardData.tree_count || clipboardData.trees?.length || 0;
                pasteBtn.textContent = '📋 Paste ' + (clipboardData.name || 'Area') + ' (' + treeCount + ' trees)';
            }
            
            // Add cross-dome indicator if needed
            if (clipboardData.source_dome_id && clipboardData.source_dome_id !== domeId) {
                pasteBtn.textContent += ' [Cross-Dome]';
                pasteBtn.classList.add('paste-btn-cross-dome');
            } else {
                pasteBtn.classList.remove('paste-btn-cross-dome');
            }
            
            console.log('✅ Paste button shown:', pasteBtn.textContent);
        } else {
            pasteBtn.style.display = 'none';
            pasteBtn.textContent = '📋 Paste Area';
            console.log('❌ No clipboard data found, hiding paste button');
        }
    }
    
    // Install the persistence system
    const persistence = ensureClipboardPersistence();
    
    // Override the updatePasteButtonDisplay function
    window.updatePasteButtonDisplay = enhancedPasteButtonDisplay;
    
    // Run enhanced display check
    setTimeout(enhancedPasteButtonDisplay, 500);
    setTimeout(enhancedPasteButtonDisplay, 2000); // Double check after page fully loads
    
    // Make functions available globally for debugging
    window.saveClipboardBackup = persistence.saveClipboardBackup;
    window.restoreClipboardFromBackup = persistence.restoreClipboardFromBackup;
    window.enhancedPasteButtonDisplay = enhancedPasteButtonDisplay;
    
    console.log('✅ Paste button persistence fix installed');
    console.log('🔧 Navigation functions overridden to preserve clipboard');
    console.log('📋 Enhanced paste button display active');
})();