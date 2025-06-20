// ============= BACKEND CLIPBOARD INTEGRATION =============

/**
 * Backend clipboard manager for cross-grid persistence
 */
class BackendClipboard {
    constructor() {
        this.isEnabled = true;
        this.currentClipboard = null;
        this.lastSaveTime = null;
        this.autoSaveEnabled = true;
        
        console.log('🔧 BackendClipboard initialized');
    }
    
    /**
     * Save clipboard data to backend
     */
    async saveToBackend(clipboardData, options = {}) {
        if (!this.isEnabled) {
            console.log('⚠️ Backend clipboard is disabled');
            return false;
        }
        
        try {
            console.log('💾 Saving clipboard to backend:', clipboardData.name);
            
            const payload = {
                clipboard_type: clipboardData.type || 'drag_area',
                name: clipboardData.name || 'Unnamed Clipboard',
                source_dome_id: window.domeId || null,
                source_farm_id: window.farmId || null,
                clipboard_content: clipboardData,
                expires_in_hours: options.expiresInHours || null
            };
            
            const response = await fetch('/api/clipboard/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log('✅ Clipboard saved to backend successfully:', result.clipboard_id);
                this.currentClipboard = result.clipboard_data;
                this.lastSaveTime = new Date();
                
                // Update UI indicators
                this.updateClipboardIndicators(true);
                
                return {
                    success: true,
                    clipboardId: result.clipboard_id,
                    data: result.clipboard_data
                };
            } else {
                console.error('❌ Failed to save clipboard to backend:', result.error);
                return { success: false, error: result.error };
            }
            
        } catch (error) {
            console.error('❌ Error saving clipboard to backend:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Load clipboard data from backend
     */
    async loadFromBackend() {
        if (!this.isEnabled) {
            console.log('⚠️ Backend clipboard is disabled');
            return null;
        }
        
        try {
            console.log('📥 Loading clipboard from backend...');
            
            const response = await fetch('/api/clipboard/load', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.success && result.has_clipboard) {
                console.log('✅ Clipboard loaded from backend:', result.clipboard_data.name);
                this.currentClipboard = result.clipboard_data;
                
                // Update UI indicators
                this.updateClipboardIndicators(true);
                
                return result.clipboard_data.clipboard_content;
            } else {
                console.log('ℹ️ No clipboard found in backend');
                this.updateClipboardIndicators(false);
                return null;
            }
            
        } catch (error) {
            console.error('❌ Error loading clipboard from backend:', error);
            return null;
        }
    }
    
    /**
     * Get clipboard status without loading full content
     */
    async getStatus() {
        if (!this.isEnabled) {
            return { hasClipboard: false };
        }
        
        try {
            const response = await fetch('/api/clipboard/status', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                return {
                    hasClipboard: result.has_clipboard,
                    data: result.clipboard_data
                };
            } else {
                return { hasClipboard: false };
            }
            
        } catch (error) {
            console.error('❌ Error getting clipboard status:', error);
            return { hasClipboard: false };
        }
    }
    
    /**
     * Clear clipboard from backend
     */
    async clearBackend() {
        if (!this.isEnabled) {
            return false;
        }
        
        try {
            console.log('🗑️ Clearing clipboard from backend...');
            
            const response = await fetch('/api/clipboard/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                console.log('✅ Clipboard cleared from backend');
                this.currentClipboard = null;
                this.updateClipboardIndicators(false);
                return true;
            } else {
                console.error('❌ Failed to clear clipboard from backend:', result.error);
                return false;
            }
            
        } catch (error) {
            console.error('❌ Error clearing clipboard from backend:', error);
            return false;
        }
    }
    
    /**
     * Auto-save clipboard data when it changes
     */
    async autoSave(clipboardData) {
        if (!this.autoSaveEnabled || !clipboardData) {
            return false;
        }
        
        // Debounce auto-save to prevent too frequent saves
        if (this.lastSaveTime && (new Date() - this.lastSaveTime) < 2000) {
            console.log('⏳ Auto-save debounced');
            return false;
        }
        
        console.log('🔄 Auto-saving clipboard to backend...');
        return await this.saveToBackend(clipboardData, { autoSave: true });
    }
    
    /**
     * Update UI indicators for clipboard status
     */
    updateClipboardIndicators(hasClipboard) {
        // Update paste button
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn) {
            if (hasClipboard) {
                pasteBtn.style.display = 'block';
                pasteBtn.classList.add('paste-btn-cross-dome');
                
                if (this.currentClipboard) {
                    const treeCount = this.currentClipboard.tree_count || 0;
                    const clipboardName = this.currentClipboard.name || 'Area';
                    pasteBtn.textContent = `📋 Paste ${clipboardName} (${treeCount} trees)`;
                }
            } else {
                pasteBtn.style.display = 'none';
                pasteBtn.classList.remove('paste-btn-cross-dome');
            }
        }
        
        // Update clipboard status indicator
        const statusIndicator = document.getElementById('clipboardStatus');
        if (statusIndicator) {
            if (hasClipboard) {
                statusIndicator.style.display = 'block';
                statusIndicator.classList.add('show');
                
                if (this.currentClipboard) {
                    const sourceInfo = this.currentClipboard.source_info || {};
                    const sourceName = sourceInfo.dome_name || sourceInfo.farm_name || 'Unknown';
                    statusIndicator.textContent = `📋 ${this.currentClipboard.name} from ${sourceName} - Click to paste`;
                }
            } else {
                statusIndicator.style.display = 'none';
                statusIndicator.classList.remove('show');
            }
        }
    }
    
    /**
     * Initialize backend clipboard on page load
     */
    async initialize() {
        console.log('🚀 Initializing backend clipboard...');
        
        // Check if there's an active clipboard
        const status = await this.getStatus();
        
        if (status.hasClipboard) {
            console.log('📋 Found active clipboard in backend');
            this.currentClipboard = status.data;
            this.updateClipboardIndicators(true);
            
            // Show notification about available clipboard
            if (typeof showStatus === 'function') {
                showStatus(`Clipboard available: ${status.data.name} (${status.data.tree_count} trees)`, 'info', 5000);
            }
        } else {
            console.log('ℹ️ No active clipboard in backend');
            this.updateClipboardIndicators(false);
        }
    }
    
    /**
     * Enhanced copy function that saves to both frontend and backend
     */
    async enhancedCopy(clipboardData) {
        console.log('📋 Enhanced copy with backend persistence...');
        
        // Save to frontend storage (existing functionality)
        if (typeof window !== 'undefined') {
            window.dragClipboard = clipboardData;
            window.clipboardArea = clipboardData;
            
            // Save to localStorage as backup
            try {
                localStorage.setItem('globalDragClipboard', JSON.stringify(clipboardData));
                localStorage.setItem(`domeClipboard_${window.domeId}`, JSON.stringify(clipboardData));
            } catch (e) {
                console.warn('⚠️ Could not save to localStorage:', e);
            }
        }
        
        // Save to backend
        const backendResult = await this.saveToBackend(clipboardData);
        
        if (backendResult.success) {
            console.log('✅ Enhanced copy completed successfully');
            return { success: true, frontend: true, backend: true };
        } else {
            console.warn('⚠️ Backend save failed, but frontend copy succeeded');
            return { success: true, frontend: true, backend: false, error: backendResult.error };
        }
    }
    
    /**
     * Enhanced load function that tries backend first, then frontend
     */
    async enhancedLoad() {
        console.log('📥 Enhanced load with backend priority...');
        
        // Try backend first
        const backendData = await this.loadFromBackend();
        if (backendData) {
            console.log('✅ Loaded from backend successfully');
            
            // Also update frontend storage
            if (typeof window !== 'undefined') {
                window.dragClipboard = backendData;
                window.clipboardArea = backendData;
            }
            
            return { success: true, data: backendData, source: 'backend' };
        }
        
        // Fallback to frontend storage
        console.log('🔄 Backend empty, trying frontend storage...');
        
        let frontendData = null;
        
        if (typeof window !== 'undefined') {
            // Try memory first
            frontendData = window.dragClipboard || window.clipboardArea;
            
            // Try localStorage if memory is empty
            if (!frontendData) {
                try {
                    const globalClipboard = localStorage.getItem('globalDragClipboard');
                    if (globalClipboard) {
                        frontendData = JSON.parse(globalClipboard);
                    }
                } catch (e) {
                    console.warn('⚠️ Could not load from localStorage:', e);
                }
            }
        }
        
        if (frontendData) {
            console.log('✅ Loaded from frontend storage');
            return { success: true, data: frontendData, source: 'frontend' };
        }
        
        console.log('ℹ️ No clipboard data found in backend or frontend');
        return { success: false, data: null, source: 'none' };
    }
}

// Create global instance
window.backendClipboard = new BackendClipboard();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (window.backendClipboard) {
        window.backendClipboard.initialize();
    }
});

// ============= INTEGRATION WITH EXISTING CLIPBOARD FUNCTIONS =============

/**
 * Enhanced version of existing copy functions
 */
function enableBackendClickToPaste() {
    console.log('🎯 Backend-enabled click to paste mode');
    
    // Load from backend first
    window.backendClipboard.enhancedLoad().then(result => {
        if (result.success) {
            window.dragClipboard = result.data;
            window.clipboardArea = result.data;
            
            // Enable click to paste mode with loaded data
            if (typeof enableClickToPaste === 'function') {
                enableClickToPaste();
            }
        } else {
            if (typeof showStatus === 'function') {
                showStatus('No clipboard data found. Copy an area first.', 'warning');
            }
        }
    });
}

function showBackendManualPasteDialog() {
    console.log('📍 Backend-enabled manual paste dialog');
    
    // Load from backend first
    window.backendClipboard.enhancedLoad().then(result => {
        if (result.success) {
            window.dragClipboard = result.data;
            window.clipboardArea = result.data;
            
            // Show manual paste dialog with loaded data
            if (typeof showManualPasteDialog === 'function') {
                showManualPasteDialog();
            }
        } else {
            if (typeof showStatus === 'function') {
                showStatus('No clipboard data found. Copy an area first.', 'warning');
            }
        }
    });
}

/**
 * Enhanced copy area function with backend persistence
 */
async function copyAreaToBackendClipboard(areaData) {
    console.log('📋 Copying area to backend clipboard:', areaData.name);
    
    const result = await window.backendClipboard.enhancedCopy(areaData);
    
    if (result.success) {
        if (typeof showStatus === 'function') {
            const message = result.backend ? 
                `Area "${areaData.name}" copied to clipboard (backend saved)` :
                `Area "${areaData.name}" copied to clipboard (frontend only)`;
            showStatus(message, result.backend ? 'success' : 'warning');
        }
        
        return true;
    } else {
        if (typeof showStatus === 'function') {
            showStatus('Failed to copy area to clipboard', 'error');
        }
        return false;
    }
}

/**
 * Enhanced clear clipboard function
 */
async function clearBackendClipboard() {
    console.log('🗑️ Clearing backend clipboard...');
    
    // Clear backend
    const backendCleared = await window.backendClipboard.clearBackend();
    
    // Clear frontend
    if (typeof window !== 'undefined') {
        window.dragClipboard = null;
        window.clipboardArea = null;
        
        try {
            localStorage.removeItem('globalDragClipboard');
            localStorage.removeItem('globalTreeClipboard');
            if (window.domeId) {
                localStorage.removeItem(`domeClipboard_${window.domeId}`);
            }
        } catch (e) {
            console.warn('⚠️ Could not clear localStorage:', e);
        }
    }
    
    // Hide paste button
    const pasteBtn = document.getElementById('pasteAreaBtn');
    if (pasteBtn) {
        pasteBtn.style.display = 'none';
    }
    
    if (typeof showStatus === 'function') {
        const message = backendCleared ? 
            'Clipboard cleared from backend and frontend' :
            'Clipboard cleared from frontend (backend clear failed)';
        showStatus(message, backendCleared ? 'success' : 'warning');
    }
    
    return backendCleared;
}

// ============= AUTO-SAVE INTEGRATION =============

/**
 * Auto-save clipboard when drag areas are copied
 */
if (typeof window !== 'undefined') {
    // Hook into existing copy functions
    const originalCopyDragArea = window.copyDragArea;
    if (originalCopyDragArea) {
        window.copyDragArea = async function(areaId) {
            const result = originalCopyDragArea.call(this, areaId);
            
            // Auto-save to backend if copy was successful
            if (result && window.dragClipboard) {
                await window.backendClipboard.autoSave(window.dragClipboard);
            }
            
            return result;
        };
    }
    
    // Hook into tree copy functions
    const originalCopyTreeToClipboard = window.copyTreeToClipboard;
    if (originalCopyTreeToClipboard) {
        window.copyTreeToClipboard = async function(tree) {
            const result = await originalCopyTreeToClipboard.call(this, tree);
            
            // Auto-save to backend if copy was successful
            if (result && window.dragClipboard) {
                await window.backendClipboard.autoSave(window.dragClipboard);
            }
            
            return result;
        };
    }
}

console.log('✅ Backend clipboard integration loaded');