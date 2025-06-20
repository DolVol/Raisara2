// ============= PASTE BUTTON FIX =============

/**
 * Enhanced paste button handler that loads from backend first
 */
function enhancedPasteButtonHandler() {
    console.log('🎯 Enhanced paste button clicked');
    
    // Load from backend first, then show paste options
    loadEnhancedClipboardFromBackend().then(clipboardData => {
        if (clipboardData) {
            console.log('📋 Clipboard loaded, showing paste options');
            
            // Ensure the clipboard data is properly set
            window.dragClipboard = clipboardData;
            window.clipboardArea = clipboardData;
            
            // Show paste options dialog
            if (typeof showPasteOptionsDialog === 'function') {
                showPasteOptionsDialog();
            } else if (typeof handlePasteButtonClick === 'function') {
                handlePasteButtonClick();
            } else {
                console.warn('⚠️ No paste dialog function found');
                if (typeof showStatus === 'function') {
                    showStatus('Paste functionality not available', 'warning');
                }
            }
        } else {
            console.log('ℹ️ No clipboard data found');
            if (typeof showStatus === 'function') {
                showStatus('No clipboard data found. Copy an area first.', 'warning');
            }
        }
    }).catch(error => {
        console.error('❌ Error in enhanced paste button handler:', error);
        if (typeof showStatus === 'function') {
            showStatus('Error loading clipboard data', 'error');
        }
    });
}

// Override the paste button click handler when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Wait for other scripts to load
    setTimeout(function() {
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn) {
            // Remove existing click handlers
            pasteBtn.onclick = null;
            
            // Add new enhanced handler
            pasteBtn.addEventListener('click', function(e) {
                e.preventDefault();
                enhancedPasteButtonHandler();
            });
            
            console.log('✅ Enhanced paste button handler installed');
        } else {
            console.log('ℹ️ Paste button not found');
        }
    }, 500);
});

// Make function globally available
window.enhancedPasteButtonHandler = enhancedPasteButtonHandler;

console.log('✅ Paste button fix loaded');