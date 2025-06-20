// ✅ UNIFIED CLIPBOARD SYSTEM - SINGLE SOURCE OF TRUTH
// This replaces all the multiple clipboard storage mechanisms with ONE centralized system

(function() {
    'use strict';
    
    console.log('🔧 Installing Unified Clipboard System...');
    
    // ✅ STEP 1: CLEAR ALL EXISTING CLIPBOARD DATA FROM ALL POSSIBLE LOCATIONS
    function clearAllClipboardData() {
        const allPossibleKeys = [
            'globalDragClipboard',
            'globalTreeClipboard', 
            'globalRegularClipboard',
            'copiedTreeData',
            'clipboardArea',
            'dragClipboard',
            'clipboardBroadcast',
            'globalDragClipboardTimestamp',
            'globalRegularClipboardTimestamp',
            'globalClipboardTimestamp',
            `domeClipboard_${domeId}`,
            `dragClipboard_dome_${domeId}`,
            `areaClipboard_dome_${domeId}`,
            `globalDragClipboard_dome_${domeId}`,
            `globalTreeClipboard_dome_${domeId}`
        ];
        
        console.log('🗑️ Clearing all existing clipboard data...');
        allPossibleKeys.forEach(key => {
            try {
                localStorage.removeItem(key);
            } catch (e) {
                // Ignore errors
            }
        });
        
        // Clear in-memory clipboard
        window.dragClipboard = null;
        window.clipboardArea = null;
        window.copiedTreeData = null;
        
        console.log('✅ All clipboard data cleared');
    }
    
    // ✅ STEP 2: UNIFIED CLIPBOARD STORAGE - SINGLE KEY ONLY
    const UNIFIED_CLIPBOARD_KEY = `unifiedClipboard_dome_${domeId}`;
    
    function saveUnifiedClipboard(clipboardData, source) {
        console.log('💾 Saving to unified clipboard:', clipboardData?.name, 'for dome', domeId);
        
        const unifiedData = {
            ...clipboardData,
            source_dome_id: domeId,
            copied_at: new Date().toISOString(),
            clipboard_source: source,
            unified_version: '1.0'
        };
        
        try {
            // ✅ ONLY USE ONE STORAGE KEY
            localStorage.setItem(UNIFIED_CLIPBOARD_KEY, JSON.stringify(unifiedData));
            console.log('✅ Saved to unified clipboard:', UNIFIED_CLIPBOARD_KEY);
            
            // Update in-memory references
            window.dragClipboard = unifiedData;
            window.clipboardArea = unifiedData;
            
            // Update paste button
            if (typeof updatePasteButtonDisplay === 'function') {
                setTimeout(updatePasteButtonDisplay, 100);
            }
            
            return unifiedData;
        } catch (e) {
            console.error('❌ Failed to save unified clipboard:', e);
            return null;
        }
    }
    
    function loadUnifiedClipboard() {
        try {
            const stored = localStorage.getItem(UNIFIED_CLIPBOARD_KEY);
            if (stored) {
                const data = JSON.parse(stored);
                if (data.source_dome_id === domeId) {
                    console.log('📋 Loaded unified clipboard:', data.name);
                    window.dragClipboard = data;
                    window.clipboardArea = data;
                    return data;
                } else {
                    console.log('⚠️ Clipboard is from different dome, not loading');
                }
            }
        } catch (e) {
            console.warn('⚠️ Error loading unified clipboard:', e);
        }
        return null;
    }
    
    // ✅ STEP 3: OVERRIDE ALL CLIPBOARD STORAGE FUNCTIONS
    
    // Override storeClipboardData
    window.storeClipboardData = function(clipboardData, source) {
        console.log('🔧 UNIFIED: storeClipboardData called');
        return saveUnifiedClipboard(clipboardData, source);
    };
    
    // Override dragSelector methods when available
    setTimeout(function() {
        if (typeof dragSelector !== 'undefined' && dragSelector) {
            if (typeof dragSelector.storeClipboardData === 'function') {
                dragSelector.storeClipboardData = function(clipboardData, source) {
                    console.log('🔧 UNIFIED: dragSelector.storeClipboardData called');
                    return saveUnifiedClipboard(clipboardData, source);
                };
            }
            
            if (typeof dragSelector.saveDragClipboardToStorage === 'function') {
                dragSelector.saveDragClipboardToStorage = function() {
                    console.log('🔧 UNIFIED: dragSelector.saveDragClipboardToStorage called');
                    if (window.dragClipboard) {
                        return saveUnifiedClipboard(window.dragClipboard, 'drag_selector');
                    }
                };
            }
        }
    }, 1000);
    
    // ✅ STEP 4: OVERRIDE CLIPBOARD LOADING
    const originalDOMContentLoaded = window.addEventListener;
    
    // Clear all data first, then load only from unified storage
    clearAllClipboardData();
    
    // Load from unified storage only
    setTimeout(function() {
        const unifiedData = loadUnifiedClipboard();
        if (unifiedData) {
            console.log('✅ Loaded clipboard from unified storage:', unifiedData.name);
        } else {
            console.log('📋 No unified clipboard data found for this dome');
        }
        
        // Update paste button
        if (typeof updatePasteButtonDisplay === 'function') {
            updatePasteButtonDisplay();
        }
    }, 500);
    
    // ✅ STEP 5: CLEAR CLIPBOARD FUNCTION
    window.clearClipboardStorage = function() {
        console.log('🗑️ Clearing unified clipboard...');
        clearAllClipboardData();
        localStorage.removeItem(UNIFIED_CLIPBOARD_KEY);
        
        if (typeof updatePasteButtonDisplay === 'function') {
            updatePasteButtonDisplay();
        }
        
        if (typeof showStatus === 'function') {
            showStatus('Clipboard cleared', 'info');
        }
        
        console.log('✅ Unified clipboard cleared');
    };
    
    // ✅ STEP 6: PROPERTY WATCHERS FOR UNIFIED SYSTEM
    let _dragClipboard = null;
    let _clipboardArea = null;
    
    Object.defineProperty(window, 'dragClipboard', {
        get: function() { return _dragClipboard; },
        set: function(value) {
            _dragClipboard = value;
            _clipboardArea = value; // Keep them in sync
            console.log('📋 UNIFIED: dragClipboard updated:', value?.name);
            if (typeof updatePasteButtonDisplay === 'function') {
                setTimeout(updatePasteButtonDisplay, 100);
            }
        }
    });
    
    Object.defineProperty(window, 'clipboardArea', {
        get: function() { return _clipboardArea; },
        set: function(value) {
            _clipboardArea = value;
            _dragClipboard = value; // Keep them in sync
            console.log('📋 UNIFIED: clipboardArea updated:', value?.name);
            if (typeof updatePasteButtonDisplay === 'function') {
                setTimeout(updatePasteButtonDisplay, 100);
            }
        }
    });
    
    console.log('✅ UNIFIED CLIPBOARD SYSTEM INSTALLED');
    console.log('📋 Using single storage key:', UNIFIED_CLIPBOARD_KEY);
    console.log('🎯 This should completely eliminate the "Copied Tree: 333" persistence issue');
    
})();