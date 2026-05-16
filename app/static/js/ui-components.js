let startX, startWidth, resizableColId;

function initResize(e, colId) {
    e.stopPropagation(); e.preventDefault();
    const col = allColumns.find(c => c.id === colId);
    resizableColId = colId;
    startX = e.pageX;
    startWidth = col.width;
    document.addEventListener('mousemove', doResize);
    document.addEventListener('mouseup', stopResize);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
}

function doResize(e) {
    const diff = e.pageX - startX;
    const colObj = allColumns.find(c => c.id === resizableColId);
    const newWidth = Math.max(50, startWidth + diff); 
    
    if (colObj.width !== newWidth) {
        colObj.width = newWidth;
        const colEl = document.getElementById(`col-${resizableColId}`);
        if (colEl) colEl.style.width = newWidth + 'px';
        
        const table = document.getElementById('jobs-table');
        const totalWidth = allColumns
            .filter(c => c.visible)
            .reduce((sum, c) => sum + c.width, 0);
        if (table) table.style.width = totalWidth + 'px';
    }
}

function stopResize() {
    document.removeEventListener('mousemove', doResize);
    document.removeEventListener('mouseup', stopResize);
    document.body.style.cursor = 'default';
    document.body.style.userSelect = 'auto';
}

function handleDragStart(e, index) { e.dataTransfer.setData('text/plain', index); e.target.classList.add('dragging'); }
function handleDragOver(e) { e.preventDefault(); }
function handleDrop(e, targetIndex) {
    e.preventDefault();
    const srcIndex = parseInt(e.dataTransfer.getData('text/plain'));
    const visibleIndices = allColumns.map((c, i) => c.visible ? i : -1).filter(i => i !== -1);
    const [movedCol] = allColumns.splice(visibleIndices[srcIndex], 1);
    allColumns.splice(visibleIndices[targetIndex], 0, movedCol);
    renderTable();
}

function showContextMenu(e, items) {
    e.preventDefault();
    e.stopPropagation();
    const menu = document.getElementById('context-menu');
    menu.style.display = 'block';
    menu.style.left = `${e.pageX}px`; menu.style.top = `${e.pageY}px`;
    menu.innerHTML = items.map(item => `
        <div class="menu-item" onclick="${item.onclick}">
            <i data-lucide="${item.icon}" style="width:14px; height:14px;"></i>
            ${item.label}
        </div>
    `).join('');
    lucide.createIcons();
    const closeMenu = () => { menu.style.display = 'none'; document.removeEventListener('click', closeMenu); };
    setTimeout(() => document.addEventListener('click', closeMenu), 10);
}

function showHeaderMenu(e) {
    const items = allColumns.map(col => ({
        label: col.label,
        icon: col.visible ? 'check-square' : 'square',
        onclick: `toggleColumn('${col.id}')`
    }));
    showContextMenu(e, items);
}

function toggleColumn(id) { 
    const col = allColumns.find(c => c.id === id); 
    col.visible = !col.visible; 
    renderTable(); 
}

function updatePresetSlider(prefix, initialVal = null) {
    const codecEl = document.getElementById(`${prefix}-video_codec`);
    if (!codecEl) return;
    const codec = codecEl.value;
    const slider = document.getElementById(`${prefix}-video_preset`);
    const valLabel = document.getElementById(`${prefix}-video_preset-val`);

    if (codec === 'libsvtav1') {
        slider.min = 0; slider.max = 13; slider.step = 1;
        if (initialVal === null) slider.value = 6;
        else slider.value = initialVal;
    } else {
        slider.min = 0; slider.max = x26xPresets.length - 1; slider.step = 1;
        if (initialVal === null) {
            slider.value = x26xPresets.indexOf('medium');
        } else {
            const idx = x26xPresets.indexOf(initialVal);
            slider.value = idx !== -1 ? idx : x26xPresets.indexOf('medium');
        }
    }
    updateSliderVal(slider);
}

function updateSliderVal(el) {
    const valLabel = document.getElementById(`${el.id}-val`);
    if (!valLabel) return;
    const prefix = el.id.includes('job-field') ? 'job-field' : 'field';
    const codec = document.getElementById(`${prefix}-video_codec`).value;

    if (codec === 'libsvtav1') {
        valLabel.innerText = el.value;
    } else {
        valLabel.innerText = x26xPresets[el.value];
    }
}

function getPresetValue(prefix) {
    const codec = document.getElementById(`${prefix}-video_codec`).value;
    const slider = document.getElementById(`${prefix}-video_preset`);
    if (codec === 'libsvtav1') return slider.value;
    return x26xPresets[slider.value];
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
