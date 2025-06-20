// Enhanced Copy/Paste Frontend Integration
// This file enhances the existing copy/paste functionality to use backend storage

// Enhanced copy function that saves to backend
async function copyDragAreaToBackend(areaId) {
    try {
        console.log(`🔄 Enhanced copy: Copying drag area ${areaId} to backend`);
        showStatus('Copying area to backend...', 'info');
        
        // Call the backend copy API
        const response = await fetch(`/api/copy_drag_area_to_backend/${domeId}/${areaId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Also store in localStorage for immediate use
            localStorage.setItem('globalDragClipboard', JSON.stringify(result.clipboard_data));
            localStorage.setItem('globalDragClipboardTimestamp', Date.now().toString());
            
            // Update frontend clipboard variables
            window.dragClipboard = result.clipboard_data;
            window.clipboardArea = result.clipboard_data;
            
            // Update paste button
            updatePasteButtonDisplay();
            
            // Show success message with stats
            const stats = result.stats;
            const message = `✅ Copied "${result.clipboard_data.name}" to backend clipboard\n` +
                          `📦 ${stats.trees_copied} trees, ${stats.breeds_found} breeds\n` +
                          `🔗 ${stats.relationships_preserved} relationships preserved`;
            
            showStatus(message, 'success');
            console.log('✅ Area copied to backend successfully:', result);
            
            return result;
        } else {
            throw new Error(result.error || 'Copy failed');
        }
        
    } catch (error) {
        console.error('❌ Error copying to backend:', error);
        showStatus(`Error copying area: ${error.message}`, 'error');
        throw error;
    }
}

// Enhanced paste function that uses backend storage with orphan handling
async function pasteDragAreaFromBackend(pasteRow, pasteCol, areaName = null, orphanHandling = null) {
    try {
        console.log(`📋 Enhanced paste: Pasting from backend to (${pasteRow}, ${pasteCol})`);
        showStatus('Pasting area from backend...', 'info');
        
        // Prepare paste data
        const pasteData = {
            paste_row: pasteRow,
            paste_col: pasteCol,
            create_trees: true
        };
        
        // Add custom name if provided
        if (areaName) {
            pasteData.name = areaName;
        }
        
        // ✅ NEW: Add orphan handling data if provided
        if (orphanHandling) {
            pasteData.orphan_handling = orphanHandling;
            console.log('🔗 Including orphan handling:', orphanHandling);
        }
        
        // Call the backend paste API
        const response = await fetch(`/api/paste_drag_area_from_backend/${domeId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(pasteData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message with stats
            const stats = result.stats;
            let message = `✅ Pasted "${result.area.name}" successfully\n` +
                         `🌳 ${stats.trees_created} trees created\n` +
                         `🔗 ${stats.relationships_created} relationships restored\n` +
                         `📍 From: ${stats.source_dome}`;
            
            // ✅ NEW: Add orphan handling results to message
            if (stats.orphaned_cuttings_handled > 0) {
                message += `\n⚠️ ${stats.orphaned_cuttings_handled} orphaned cuttings handled (${stats.orphan_handling_mode})`;
                if (stats.preserved_original_relationships > 0) {
                    message += `\n🔄 ${stats.preserved_original_relationships} original relationships preserved`;
                }
                if (stats.linked_to_existing_mothers > 0) {
                    message += `\n🔗 ${stats.linked_to_existing_mothers} linked to existing mothers`;
                }
                if (stats.independent_cuttings_converted > 0) {
                    message += `\n🌱 ${stats.independent_cuttings_converted} converted to independent trees`;
                }
            }
            
            // ✅ NEW: Add cutting tree transfer information
            if (stats.transferred_cuttings > 0) {
                message += `\n🔄 ${stats.transferred_cuttings} cutting trees transferred to new mothers`;
            }
            
            showStatus(message, 'success');
            console.log('✅ Area pasted from backend successfully:', result);
            
            // ✅ FIX: Force page reload to ensure trees are visible
            setTimeout(() => {
                // ✅ PRESERVE: Save clipboard data before reload
                const savedClipboard = window.dragClipboard || window.clipboardArea;
                
                console.log('🔄 Forcing page reload to show pasted trees...');
                
                // Store clipboard in localStorage to survive page reload
                if (savedClipboard) {
                    try {
                        localStorage.setItem('globalDragClipboard', JSON.stringify(savedClipboard));
                        localStorage.setItem('globalDragClipboardTimestamp', Date.now().toString());
                        console.log('💾 Clipboard saved to localStorage before reload');
                    } catch (e) {
                        console.warn('⚠️ Could not save clipboard to localStorage:', e);
                    }
                }
                
                setTimeout(() => {
                    location.reload();
                }, 500);
            }, 1000);
            
            return result;
        } else {
            throw new Error(result.error || 'Paste failed');
        }
        
    } catch (error) {
        console.error('❌ Error pasting from backend:', error);
        showStatus(`Error pasting area: ${error.message}`, 'error');
        throw error;
    }
}

// Check clipboard status from backend
async function getBackendClipboardStatus() {
    try {
        const response = await fetch('/api/get_clipboard_status');
        const result = await response.json();
        
        if (result.success) {
            return result;
        } else {
            console.warn('Failed to get clipboard status:', result.error);
            return { success: true, has_clipboard: false };
        }
        
    } catch (error) {
        console.error('Error getting clipboard status:', error);
        return { success: true, has_clipboard: false };
    }
}

// Clear backend clipboard
async function clearBackendClipboard() {
    try {
        const response = await fetch('/api/clear_clipboard', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Also clear localStorage
            localStorage.removeItem('globalDragClipboard');
            localStorage.removeItem('globalDragClipboardTimestamp');
            
            // Clear frontend variables
            window.dragClipboard = null;
            window.clipboardArea = null;
            
            // Update paste button
            updatePasteButtonDisplay();
            
            showStatus('Clipboard cleared', 'info');
            console.log('✅ Clipboard cleared successfully');
            
            return result;
        } else {
            throw new Error(result.error || 'Clear failed');
        }
        
    } catch (error) {
        console.error('❌ Error clearing clipboard:', error);
        showStatus(`Error clearing clipboard: ${error.message}`, 'error');
        throw error;
    }
}

// Enhanced copy function that replaces the existing one
function enhancedCopyDragArea(areaId) {
    // Use the backend copy function
    return copyDragAreaToBackend(areaId);
}

// Enhanced paste function for click-to-paste
async function enhancedPasteDragArea(row, col) {
    try {
        // First check if we have clipboard data in backend
        const clipboardStatus = await getBackendClipboardStatus();
        
        if (clipboardStatus.has_clipboard) {
            // Use backend paste
            return await pasteDragAreaFromBackend(row, col);
        } else {
            // Fallback to existing frontend paste if available
            if (window.dragClipboard || window.clipboardArea) {
                console.log('📋 Using frontend clipboard as fallback');
                return await pasteDragArea(row, col); // Call existing function
            } else {
                throw new Error('No clipboard data available');
            }
        }
        
    } catch (error) {
        console.error('❌ Enhanced paste error:', error);
        showStatus(`Paste failed: ${error.message}`, 'error');
        throw error;
    }
}

// Initialize enhanced clipboard on page load
async function initializeEnhancedClipboard() {
    try {
        console.log('🔄 Initializing enhanced clipboard...');
        
        // Check backend clipboard status
        const clipboardStatus = await getBackendClipboardStatus();
        
        if (clipboardStatus.has_clipboard) {
            const info = clipboardStatus.clipboard_info;
            console.log(`📋 Found backend clipboard: "${info.name}" (${info.tree_count} trees)`);
            
            // Update paste button to show backend clipboard
            const pasteBtn = document.getElementById('pasteAreaBtn');
            if (pasteBtn) {
                pasteBtn.style.display = 'block';
                pasteBtn.textContent = `📋 Paste "${info.name}" (${info.tree_count} trees) [Backend]`;
                pasteBtn.classList.add('paste-btn-backend');
            }
            
            // Show notification about available clipboard
            showStatus(`Backend clipboard available: "${info.name}" (${info.tree_count} trees)`, 'info');
        } else {
            console.log('📭 No backend clipboard data found');
        }
        
    } catch (error) {
        console.error('⚠️ Error initializing enhanced clipboard:', error);
    }
}

// Override existing copy function if it exists
if (typeof window.copyDragAreaToBackend === 'undefined') {
    window.copyDragAreaToBackend = copyDragAreaToBackend;
}

if (typeof window.pasteDragAreaFromBackend === 'undefined') {
    window.pasteDragAreaFromBackend = pasteDragAreaFromBackend;
}

// Add enhanced functions to global scope
window.enhancedCopyDragArea = enhancedCopyDragArea;
window.enhancedPasteDragArea = enhancedPasteDragArea;
window.getBackendClipboardStatus = getBackendClipboardStatus;
window.clearBackendClipboard = clearBackendClipboard;
window.initializeEnhancedClipboard = initializeEnhancedClipboard;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Enhanced copy/paste frontend loaded');
    
    // Initialize enhanced clipboard after a short delay
    setTimeout(initializeEnhancedClipboard, 1000);
});

// Add CSS for backend clipboard indicator
const style = document.createElement('style');
style.textContent = `
    .paste-btn-backend {
        background: linear-gradient(45deg, #28a745, #20c997) !important;
        border-color: #28a745 !important;
        box-shadow: 0 2px 4px rgba(40, 167, 69, 0.3) !important;
    }
    
    .paste-btn-backend:hover {
        background: linear-gradient(45deg, #218838, #1ea080) !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(40, 167, 69, 0.4) !important;
    }
`;
document.head.appendChild(style);

console.log('🚀 Enhanced copy/paste system initialized');