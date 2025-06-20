// ============= CROSS-GRID CLIPBOARD FUNCTIONALITY =============

/**
 * Enhanced clipboard functionality that persists across grid pages
 */
class CrossGridClipboard {
    constructor() {
        this.isEnabled = true;
        this.autoSaveEnabled = true;
        console.log('🔧 CrossGridClipboard initialized');
        
        // Initialize on page load
        this.initializeOnPageLoad();
    }
    
    /**
     * Save clipboard data to backend
     */
    async saveToBackend(clipboardData) {
        if (!this.isEnabled || !clipboardData) {
            return false;
        }
        
        try {
            console.log('💾 Saving clipboard to backend:', clipboardData.name || 'Unnamed');
            
            const payload = {
                clipboard_type: clipboardData.type || 'drag_area',
                name: clipboardData.name || 'Copied Area',
                source_dome_id: window.domeId || null,
                source_farm_id: window.farmId || null,
                clipboard_content: clipboardData
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
                console.log('✅ Clipboard saved to backend successfully');
                this.updatePasteButton(true, clipboardData);
                return true;
            } else {
                console.error('❌ Failed to save clipboard to backend:', result.error);
                return false;
            }
            
        } catch (error) {
            console.error('❌ Error saving clipboard to backend:', error);
            return false;
        }
    }
    
    /**
     * Load clipboard data from backend
     */
    async loadFromBackend() {
        if (!this.isEnabled) {
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
                
                const clipboardContent = result.clipboard_data.clipboard_content;
                
                // Update frontend clipboard variables
                window.dragClipboard = clipboardContent;
                window.clipboardArea = clipboardContent;
                
                // Update localStorage as backup
                try {
                    localStorage.setItem('globalDragClipboard', JSON.stringify(clipboardContent));
                } catch (e) {
                    console.warn('⚠️ Could not save to localStorage:', e);
                }
                
                this.updatePasteButton(true, clipboardContent);
                return clipboardContent;
            } else {
                console.log('ℹ️ No clipboard found in backend');
                this.updatePasteButton(false);
                return null;
            }
            
        } catch (error) {
            console.error('❌ Error loading clipboard from backend:', error);
            return null;
        }
    }
    
    /**
     * Update paste button visibility and text
     */
    updatePasteButton(hasClipboard, clipboardData = null) {
        const pasteBtn = document.getElementById('pasteAreaBtn');
        if (pasteBtn) {
            if (hasClipboard && clipboardData) {
                pasteBtn.style.display = 'block';
                pasteBtn.classList.add('paste-btn-cross-dome');
                
                const treeCount = clipboardData.tree_count || clipboardData.trees?.length || 0;
                const clipboardName = clipboardData.name || 'Area';
                pasteBtn.textContent = `📋 Paste ${clipboardName} (${treeCount} trees)`;
                
                // Show notification
                if (typeof showStatus === 'function') {
                    showStatus(`Clipboard available: ${clipboardName} (${treeCount} trees)`, 'info', 3000);
                }
            } else {
                pasteBtn.style.display = 'none';
                pasteBtn.classList.remove('paste-btn-cross-dome');
            }
        }
    }
    
    /**
     * Enhanced copy function that automatically saves to backend
     */
    async enhancedCopy(clipboardData) {
        console.log('📋 Enhanced copy with backend persistence...');
        
        // Save to frontend storage (existing functionality)
        window.dragClipboard = clipboardData;
        window.clipboardArea = clipboardData;
        
        // Save to localStorage as backup
        try {
            localStorage.setItem('globalDragClipboard', JSON.stringify(clipboardData));
            if (window.domeId) {
                localStorage.setItem(`domeClipboard_${window.domeId}`, JSON.stringify(clipboardData));
            }
        } catch (e) {
            console.warn('⚠️ Could not save to localStorage:', e);
        }
        
        // Save to backend
        const backendSaved = await this.saveToBackend(clipboardData);
        
        if (backendSaved) {
            console.log('✅ Enhanced copy completed successfully');
            if (typeof showStatus === 'function') {
                showStatus(`Area "${clipboardData.name || 'Copied'}" saved to clipboard`, 'success');
            }
        } else {
            console.warn('⚠️ Backend save failed, but frontend copy succeeded');
            if (typeof showStatus === 'function') {
                showStatus(`Area copied (frontend only)`, 'warning');
            }
        }
        
        return backendSaved;
    }
    
    /**
     * Initialize clipboard on page load
     */
    async initializeOnPageLoad() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.checkForClipboard());
        } else {
            this.checkForClipboard();
        }
    }
    
    /**
     * Check for existing clipboard data on page load
     */
    async checkForClipboard() {
        console.log('🔍 Checking for existing clipboard data...');
        
        // Try to load from backend first
        const backendData = await this.loadFromBackend();
        
        if (backendData) {
            console.log('📋 Found clipboard data in backend');
            return;
        }
        
        // Fallback to localStorage
        try {
            const localData = localStorage.getItem('globalDragClipboard');
            if (localData) {
                const clipboardData = JSON.parse(localData);
                console.log('📋 Found clipboard data in localStorage');
                
                window.dragClipboard = clipboardData;
                window.clipboardArea = clipboardData;
                
                this.updatePasteButton(true, clipboardData);
                
                // Auto-save to backend for future cross-grid access
                await this.saveToBackend(clipboardData);
            }
        } catch (e) {
            console.warn('⚠️ Could not load from localStorage:', e);
        }
    }
    
    /**
     * Clear clipboard from both frontend and backend
     */
    async clearClipboard() {
        console.log('🗑️ Clearing clipboard...');
        
        // Clear frontend
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
        
        // Clear backend
        try {
            const response = await fetch('/api/clipboard/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            if (result.success) {
                console.log('✅ Clipboard cleared from backend');
            }
        } catch (error) {
            console.error('❌ Error clearing backend clipboard:', error);
        }
        
        this.updatePasteButton(false);
        
        if (typeof showStatus === 'function') {
            showStatus('Clipboard cleared', 'info');
        }
    }
}

// Create global instance
window.crossGridClipboard = new CrossGridClipboard();

// ============= INTEGRATION WITH EXISTING FUNCTIONS =============

// Hook into existing copy functions to automatically save to backend
document.addEventListener('DOMContentLoaded', function() {
    // Override the existing copyDragArea function if it exists
    if (typeof window.copyDragArea === 'function') {
        const originalCopyDragArea = window.copyDragArea;
        window.copyDragArea = async function(areaId) {
            const result = originalCopyDragArea.call(this, areaId);
            
            // Auto-save to backend if copy was successful
            if (result && window.dragClipboard) {
                await window.crossGridClipboard.enhancedCopy(window.dragClipboard);
            }
            
            return result;
        };
    }
    
    // Override the existing copyTreeToClipboard function if it exists
    if (typeof window.copyTreeToClipboard === 'function') {
        const originalCopyTreeToClipboard = window.copyTreeToClipboard;
        window.copyTreeToClipboard = async function(tree) {
            const result = await originalCopyTreeToClipboard.call(this, tree);
            
            // Auto-save to backend if copy was successful
            if (result && window.dragClipboard) {
                await window.crossGridClipboard.enhancedCopy(window.dragClipboard);
            }
            
            return result;
        };
    }
    
    // Override the paste button click handler
    const pasteBtn = document.getElementById('pasteAreaBtn');
    if (pasteBtn) {
        pasteBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            // Try to load from backend first
            const clipboardData = await window.crossGridClipboard.loadFromBackend();
            
            if (clipboardData) {
                // Show paste options dialog with loaded data
                if (typeof showPasteOptionsDialog === 'function') {
                    showPasteOptionsDialog();
                } else if (typeof handlePasteButtonClick === 'function') {
                    handlePasteButtonClick();
                }
            } else {
                if (typeof showStatus === 'function') {
                    showStatus('No clipboard data found. Copy an area first.', 'warning');
                }
            }
        });
    }
    
    // Override the clear clipboard button if it exists
    const clearBtn = document.querySelector('[onclick*="clearClipboard"]');
    if (clearBtn) {
        clearBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            await window.crossGridClipboard.clearClipboard();
        });
    }
});

console.log('✅ Cross-grid clipboard functionality loaded');
