// ✅ CRITICAL FIX FOR "Copied Tree: 333" PERSISTENCE ISSUE
// Add this JavaScript code to your grid.html file to fix the clipboard contamination

// ✅ OVERRIDE CLIPBOARD STORAGE: Fix the root cause of clipboard contamination
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
            localStorage.setItem(`domeClipboard_${domeId}`, JSON.stringify(enhancedClipboardData));
            console.log('✅ Saved dome-specific clipboard:', `domeClipboard_${domeId}`);
            
            // ✅ PRIORITY 2: Store global clipboard for cross-dome pasting (when intended)
            localStorage.setItem('globalDragClipboard', JSON.stringify(enhancedClipboardData));
            localStorage.setItem('globalClipboardTimestamp', Date.now().toString());
            console.log('✅ Saved global clipboard with dome ID:', enhancedClipboardData.source_dome_id);
            
            console.log('✅ Clipboard saved successfully with dome isolation');
            
        } catch (e) {
            console.warn('⚠️ Could not save clipboard to localStorage:', e);
        }
        
        // Update paste button immediately
        if (typeof updatePasteButtonDisplay === 'function') {
            setTimeout(updatePasteButtonDisplay, 100);
        }
    };
    
    console.log('✅ storeClipboardData function overridden with dome isolation');
})();

// ✅ ALSO OVERRIDE DRAG SELECTOR METHODS
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

console.log('✅ CRITICAL FIX APPLIED: This should resolve the "Copied Tree: 333" persistence issue');