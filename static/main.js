function addDome() {
  const domeId = Date.now(); // Temporary ID
  const domeDiv = document.createElement('div');
  domeDiv.innerHTML = `
    <h2>โดมใหม่ ${domeId}</h2>
    <button class="add-row-btn" data-dome-id="${domeId}">➕ แถว</button>
    <div class="rows"></div>
  `;
  document.getElementById('domes').appendChild(domeDiv);
}

function addRow(domeId, button) {
  const rowContainer = button.parentElement.querySelector('.rows');
  const rowId = Date.now();
  rowContainer.innerHTML += `
    <div class="row" data-row-id="${rowId}">
      แถว ${rowId}
      <button onclick="deleteRow(${rowId})">ลบ</button>
    </div>
  `;
}

function deleteRow(rowId) {
  document.querySelector(`[data-row-id="${rowId}"]`).remove();
}

// Event delegation for dynamically added elements
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('add-row-btn')) {
    const domeId = e.target.dataset.domeId;
    addRow(domeId, e.target);
  }
});

async function addTree(rowId, btn) {
  const res = await axios.post('/add_tree', { row_id: rowId });
  const treeBtn = document.createElement('button');
  treeBtn.innerText = res.data.name;
  treeBtn.onclick = () => openTreeForm(res.data.id);
  btn.nextElementSibling.appendChild(treeBtn);
}

function openTreeForm(treeId) {
  const form = document.createElement('form');
  form.innerHTML = `
    <h3>แก้ไขต้นไม้</h3>
    <input name="name" placeholder="ชื่อ"><br>
    <textarea name="info" placeholder="ข้อมูลอื่นๆ"></textarea><br>
    <input type="file" name="image"><br>
    <button>บันทึก</button>
  `;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    formData.append('id', treeId);
    await axios.post('/update_tree', formData);
    alert('บันทึกแล้ว!');
    form.remove();
  };
  document.body.appendChild(form);
}
function addRow(domeId, button) {
  const rowName = prompt("ตั้งชื่อแถว:");
  axios.post('/add_row', {
    dome_id: domeId,
    name: rowName || 'แถวใหม่'
  }).then(res => {
    const rowDiv = document.createElement('div');
    rowDiv.innerHTML = `
      <h4>${res.data.name}</h4>
      <button onclick="addTree(${res.data.id}, this)">➕ ต้นไม้</button>
      <div class="trees"></div>
    `;
    button.parentElement.querySelector('.rows').appendChild(rowDiv);
  });
}
function addTree(rowId, button) {
  const name = prompt("ชื่อต้นไม้:");
  axios.post('/add_tree', {
    row_id: rowId,
    name: name || 'ต้นไม้ใหม่'
  }).then(res => {
    const treeDiv = document.createElement('div');
    treeDiv.innerHTML = `
      🌱 <span onclick="editTree(${res.data.id})" style="cursor:pointer;">${res.data.name}</span>
    `;
    button.parentElement.querySelector('.trees').appendChild(treeDiv);
  });
}
async function moveDome(domeId, direction) {
    const domeCard = document.querySelector(`[data-dome-id="${domeId}"]`);
    domeCard.classList.add('moving');
    
    try {
        const response = await fetch(`/move_dome/${domeId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ direction })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Update stored coordinates
            domeCard.dataset.x = data.x;
            domeCard.dataset.y = data.y;
            // Visual reordering
            const grid = document.getElementById('domes');
            grid.insertBefore(domeCard, domeCard.previousElementSibling);
        }
    } catch (error) {
        console.error('Error:', error);
    } finally {
        domeCard.classList.remove('moving');
    }
}

async function deleteDome(domeId) {
    if (confirm('คุณแน่ใจหรือไม่ว่าต้องการลบโดมนี้?')) {
        try {
            await fetch(`/delete_dome/${domeId}`, {
                method: 'DELETE'
            });
            document.querySelector(`[data-dome-id="${domeId}"]`).remove();
        } catch (error) {
            console.error('Error:', error);
        }
    }
}

function createDomeCard(dome) {
    const card = document.createElement('div');
    card.className = 'dome-card';
    card.dataset.domeId = dome.id;
    card.innerHTML = `
        <div class="dome-header">
            <h3>${dome.name}</h3>
        </div>
        <div class="dome-controls">
            <button class="move-btn" onclick="moveDome(${dome.id}, 'left')">←</button>
            <div class="vertical-controls">
                <button class="move-btn" onclick="moveDome(${dome.id}, 'up')">↑</button>
                <button class="move-btn" onclick="moveDome(${dome.id}, 'down')">↓</button>
            </div>
            <button class="move-btn" onclick="moveDome(${dome.id}, 'right')">→</button>
            <button class="delete-btn" onclick="deleteDome(${dome.id})">ลบ</button>
        </div>
        <table class="dome-table">
            <tbody></tbody>
        </table>
    `;
    return card;
}

async function deleteDome(domeId) {
    if (confirm('คุณแน่ใจหรือไม่ว่าต้องการลบโดมนี้?')) {
        try {
            await fetch(`/delete_dome/${domeId}`, { method: 'DELETE' });
            document.querySelector(`[data-dome-id="${domeId}"]`).remove();
        } catch (error) {
            console.error('Error:', error);
        }
    }
}

// Initial load
document.addEventListener('DOMContentLoaded', async () => {
    const res = await fetch('/domes');
    const domes = await res.json();
    domes.forEach(dome => createDomeCard(dome));
});
let draggedDome = null;

function onDragStart(e) {
    draggedDome = e.target.closest('.dome-card');
    e.dataTransfer.effectAllowed = 'move';
}

function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}

async function onDrop(e) {
    e.preventDefault();
    const targetDome = e.target.closest('.dome-card');
    if (!draggedDome || !targetDome || draggedDome === targetDome) return;
    
    // Swap positions in database
    const success = await swapDomes(
        draggedDome.dataset.domeId, 
        targetDome.dataset.domeId
    );
    
    if (success) {
        // Swap DOM elements
        const temp = document.createElement('div');
        draggedDome.parentNode.insertBefore(temp, draggedDome);
        targetDome.parentNode.insertBefore(draggedDome, targetDome);
        temp.parentNode.insertBefore(targetDome, temp);
        temp.remove();
    }
    
    draggedDome = null;
}

async function swapDomes(domeId1, domeId2) {
    try {
        const response = await fetch(`/swap_domes/${domeId1}/${domeId2}`, {
            method: 'POST'
        });
        return response.ok;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

function startEditing(element) {
    const input = document.createElement('input');
    input.type = 'text';
    input.value = element.innerText;
    input.className = 'dome-name-input';
    
    input.onblur = async () => {
        const newName = input.value.trim();
        if (newName && newName !== element.innerText) {
            const success = await updateDomeName(
                element.closest('.dome-card').dataset.domeId,
                newName
            );
            if (success) element.innerText = newName;
        }
        element.parentNode.replaceChild(element, input);
    };
    
    element.parentNode.replaceChild(input, element);
    input.focus();
}

async function updateDomeName(domeId, newName) {
    try {
        const response = await fetch(`/update_dome/${domeId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: newName })
        });
        return response.ok;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}
async function saveTreeInfo() {
    // ...
    const url = currentTreeId ? 
        `/update_tree/${currentTreeId}` : 
        `/add_tree/${currentDomeId}/${currentRow}/${currentCol}`;
    // ...
}
async function moveDome(domeId, direction) {
    try {
        const response = await fetch(`/move_dome/${domeId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ direction: direction })
        });
        
        if (response.ok) {
            // Refresh positions
            const domesContainer = document.getElementById('domes');
            domesContainer.innerHTML = '';
            const response = await fetch('/domes');
            const domes = await response.json();
            domes.forEach(dome => createDomeCard(dome));
        }
    } catch (error) {
        console.error('Error:', error);
    }
}
// In your frontend JavaScript
function showAddDomeForm(row, col) {
  const domeName = prompt('Enter dome name:');
  if (domeName) {
    fetch('/add_dome', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: domeName,
        grid_row: row,  // Changed from row
        grid_col: col   // Changed from col
      })
    })
    .then(response => response.json())
    .then(dome => {
      location.reload();
    });
  }
}
function handleDomeClick(domeId) {
    window.location.href = `/dome_info/${domeId}`;
}

// Update your dome elements to use this function
document.querySelectorAll('.dome').forEach(dome => {
    dome.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent triggering cell click
        const domeId = dome.dataset.domeId;
        handleDomeClick(domeId);
    });
});