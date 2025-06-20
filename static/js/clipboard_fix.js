// ============= CLIPBOARD DATA FIX =============

/**
 * Enhanced clipboard data processing to fix the tree count issue
 */
function enhanceClipboardData(backendResult) {
    if (!backendResult || !backendResult.clipboard_data) {
        return null;
    }
    
    let clipboardContent = backendResult.clipboard_data.clipboard_content;
    
    // ✅ ENHANCED: Ensure proper data structure and fix missing tree data
    if (clipboardContent && typeof clipboardContent === 'object') {
        // Add metadata from backend if missing
        if (!clipboardContent.name && backendResult.clipboard_data.name) {
            clipboardContent.name = backendResult.clipboard_data.name;
        }
        if (!clipboardContent.tree_count && backendResult.clipboard_data.tree_count) {
            clipboardContent.tree_count = backendResult.clipboard_data.tree_count;
        }
        if (!clipboardContent.width && backendResult.clipboard_data.width) {
            clipboardContent.width = backendResult.clipboard_data.width;
        }
        if (!clipboardContent.height && backendResult.clipboard_data.height) {
            clipboardContent.height = backendResult.clipboard_data.height;
        }
        
        // ✅ CRITICAL: Ensure trees data is properly structured
        if (!clipboardContent.trees && !clipboardContent.trees_data) {
            // Try to extract trees from various possible locations
            if (clipboardContent.data && clipboardContent.data.trees) {
                clipboardContent.trees = clipboardContent.data.trees;
                clipboardContent.trees_data = clipboardContent.data.trees;
            } else if (clipboardContent.clipboard_content && clipboardContent.clipboard_content.trees) {
                clipboardContent.trees = clipboardContent.clipboard_content.trees;
                clipboardContent.trees_data = clipboardContent.clipboard_content.trees;
            }
        }
        
        // ✅ ENHANCED: Add source information for cross-dome tracking
        clipboardContent.source_dome_id = backendResult.clipboard_data.source_dome_id;
        clipboardContent.source_farm_id = backendResult.clipboard_data.source_farm_id;
        clipboardContent.clipboard_source = 'backend_api';
        clipboardContent.timestamp = Date.now();
        
        // Add source dome name for display
        if (backendResult.clipboard_data.source_info) {
            clipboardContent.source_dome_name = backendResult.clipboard_data.source_info.dome_name;
            clipboardContent.source_farm_name = backendResult.clipboard_data.source_info.farm_name;
        }
        
        console.log('📋 Enhanced clipboard data:', {
            name: clipboardContent.name,
            tree_count: clipboardContent.tree_count,
            trees_length: clipboardContent.trees?.length,
            source_dome_id: clipboardContent.source_dome_id
        });
        
        return clipboardContent;
    }
    
    console.warn('⚠️ Invalid clipboard content structure:', clipboardContent);
    return null;
}

/**
 * Enhanced load from backend function
 */
async function loadEnhancedClipboardFromBackend() {
    try {
        console.log('📥 Loading enhanced clipboard from backend...');
        
        const response = await fetch('/api/clipboard/load', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const result = await response.json();
        
        if (result.success && result.has_clipboard) {
            console.log('✅ Clipboard loaded from backend:', result.clipboard_data.name);
            
            const enhancedClipboard = enhanceClipboardData(result);
            
            if (enhancedClipboard) {
                // Update frontend clipboard variables
                window.dragClipboard = enhancedClipboard;
                window.clipboardArea = enhancedClipboard;
                
                // Update localStorage as backup
                try {
                    localStorage.setItem('globalDragClipboard', JSON.stringify(enhancedClipboard));
                } catch (e) {
                    console.warn('⚠️ Could not save to localStorage:', e);
                }
                
                // Update paste button
                const pasteBtn = document.getElementById('pasteAreaBtn');
                if (pasteBtn) {
                    pasteBtn.style.display = 'block';
                    pasteBtn.classList.add('paste-btn-cross-dome');
                    
                    const treeCount = enhancedClipboard.tree_count || enhancedClipboard.trees?.length || 0;
                    const clipboardName = enhancedClipboard.name || 'Area';
                    pasteBtn.textContent = `📋 Paste ${clipboardName} (${treeCount} trees)`;
                    
                    // Show notification
                    if (typeof showStatus === 'function') {
                        showStatus(`Clipboard available: ${clipboardName} (${treeCount} trees)`, 'info', 3000);
                    }
                }
                
                return enhancedClipboard;
            }
        } else {
            console.log('ℹ️ No clipboard found in backend');
            return null;
        }
        
    } catch (error) {
        console.error('❌ Error loading clipboard from backend:', error);
        return null;
    }
}

// Override the existing function if it exists
if (window.crossGridClipboard) {
    window.crossGridClipboard.loadFromBackend = loadEnhancedClipboardFromBackend;
}

// Make functions globally available
window.enhanceClipboardData = enhanceClipboardData;
window.loadEnhancedClipboardFromBackend = loadEnhancedClipboardFromBackend;

// Auto-load on page load
document.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for other scripts to load
    setTimeout(async function() {
        console.log('🔍 Auto-loading clipboard on page load...');
        const clipboardData = await loadEnhancedClipboardFromBackend();
        if (clipboardData) {
            console.log('📋 Successfully loaded clipboard on page load');
        }
    }, 1000);
});

console.log('✅ Clipboard fix loaded');