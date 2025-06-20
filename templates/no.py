async function loadAreasFromBackend() {
    try {
        console.log('🔄 Loading areas from backend...');
        
        // ✅ Load drag areas
        try {
            const dragResponse = await fetch(`/api/get_drag_areas/${domeId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (dragResponse.ok) {
                const dragResult = await dragResponse.json();
                
                if (dragResult.success && dragResult.drag_areas) {
                    // ✅ Convert backend data to frontend format
                    dragAreas = dragResult.drag_areas.map(area => ({
                        id: area.id,
                        name: area.name,
                        color: area.color || '#007bff',
                        width: area.width,
                        height: area.height,
                        minRow: area.minRow,
                        maxRow: area.maxRow,
                        minCol: area.minCol,
                        maxCol: area.maxCol,
                        trees: area.trees || [],
                        tree_count: area.tree_count || 0,
                        visible: area.visible !== false,
                        created_at: area.createdAt || area.created_at,
                        saved_to_db: true
                    }));
                    
                    console.log(`✅ Loaded ${dragAreas.length} drag areas from backend`);
                } else {
                    console.log('No drag areas found in backend');
                    dragAreas = [];
                }
            } else {
                console.warn('❌ Failed to load drag areas from backend:', dragResponse.status);
                dragAreas = [];
            }
        } catch (dragError) {
            console.error('❌ Error loading drag areas:', dragError);
            dragAreas = [];
        }
        
        // ✅ Load regular areas
        try {
            const regularResponse = await fetch(`/api/regular_areas/${domeId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (regularResponse.ok) {
                const regularResult = await regularResponse.json();
                
                if (regularResult.success && regularResult.regular_areas) {
                    // ✅ Convert backend data to frontend format
                    areas = regularResult.regular_areas.map(area => ({
                        id: area.id,
                        name: area.name,
                        color: area.color || '#28a745',
                        width: area.width,
                        height: area.height,
                        min_row: area.min_row,
                        max_row: area.max_row,
                        min_col: area.min_col,
                        max_col: area.max_col,
                        cells: area.cells || [],
                        tree_count: area.tree_count || 0,
                        visible: area.visible !== false,
                        created_at: area.created_at,
                        saved_to_db: true
                    }));
                    
                    console.log(`✅ Loaded ${areas.length} regular areas from backend`);
                } else {
                    console.log('No regular areas found in backend');
                    areas = [];
                }
            } else {
                console.warn('❌ Failed to load regular areas from backend:', regularResponse.status);
                areas = [];
            }
        } catch (regularError) {
            console.error('❌ Error loading regular areas:', regularError);
            areas = [];
        }
        
        // ✅ Update displays after loading
        if (typeof updateDragAreasDisplay === 'function') {
            updateDragAreasDisplay();
        }
        if (typeof updateAreasDisplay === 'function') {
            updateAreasDisplay();
        }
        
        // ✅ CRITICAL: Re-render grid to show loaded areas
        renderGrid();
        
        console.log(`✅ Areas loading completed: ${dragAreas.length} drag areas, ${areas.length} regular areas`);
        
        return true;
        
    } catch (error) {
        console.error('❌ Error loading areas from backend:', error);
        return false;
    }
}
setTimeout(() => {
    console.log('🔄 Force rendering all areas after backend load...');
    forceRenderAllAreas();
}, 100);