let currentBrowserPath = '';
let selectedFiles = new Set();
let currentDirItems = [];

async function browse(relPath) {
    currentBrowserPath = relPath;
    const res = await fetch(`/api/files?path=${encodeURIComponent(relPath)}`);
    const data = await res.json();
    
    if (data.error) {
        console.error(data.error);
        return;
    }

    currentDirItems = data.items;
    renderBreadcrumbs(relPath);
    const browser = document.getElementById('file-browser');
    if (browser) {
        browser.innerHTML = data.items.map(item => {
            const fullPath = '/media/' + item.path.replace(/\\/g, '/');
            const isSelected = selectedFiles.has(fullPath);
            const selectionIcon = isSelected ? 'square-check' : 'square';
            
            return `
                <div class="browser-item ${item.is_dir ? 'dir' : 'file'} ${isSelected ? 'selected' : ''}" 
                     onclick="${item.is_dir ? `browse('${item.path.replace(/\\/g, '/')}')` : `toggleFileSelection('${fullPath}', event)`}">
                    ${!item.is_dir ? `
                        <div class="selection-icon" onclick="event.stopPropagation(); toggleFileSelection('${fullPath}')">
                            <i data-lucide="${selectionIcon}"></i>
                        </div>
                    ` : '<div style="width: 20px;"></div>'}
                    <i data-lucide="${item.is_dir ? 'folder' : 'file-video'}"></i>
                    <span>${item.name}</span>
                </div>
            `;
        }).join('');
        lucide.createIcons();
    }
}

function isVideoFile(name) {
    const ext = name.split('.').pop().toLowerCase();
    return ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v'].includes(ext);
}

function renderBreadcrumbs(path) {
    const container = document.getElementById('breadcrumbs');
    if (!container) return;
    const parts = path.split('/').filter(p => p);
    
    const hasVideos = currentDirItems.some(item => !item.is_dir && isVideoFile(item.name));
    const allSelected = hasVideos && currentDirItems
        .filter(item => !item.is_dir && isVideoFile(item.name))
        .every(item => selectedFiles.has('/media/' + item.path.replace(/\\/g, '/')));
    
    const selectAllIcon = allSelected ? 'square-check' : 'square';
    
    let html = '';
    
    if (hasVideos) {
        html += `
            <div class="selection-icon select-all" onclick="toggleSelectAllVideos(!${allSelected})" title="Select all video files">
                <i data-lucide="${selectAllIcon}"></i>
            </div>
        `;
    } else {
        html += `<div style="width: 24px;"></div>`;
    }
    
    html += `
        <div class="breadcrumb-header">
            <span class="breadcrumb-item" onclick="browse('')">/media</span>
    `;
    
    let current = '';
    parts.forEach((p, i) => {
        current += (i === 0 ? '' : '/') + p;
        html += ` <span class="breadcrumb-separator">/</span> <span class="breadcrumb-item" onclick="browse('${current}')">${p}</span>`;
    });
    
    html += `</div>`;
    
    container.innerHTML = html;
    lucide.createIcons();
}

function toggleFileSelection(path, event) {
    if (event) event.stopPropagation();
    
    if (selectedFiles.has(path)) {
        selectedFiles.delete(path);
    } else {
        selectedFiles.add(path);
    }
    updateSelectionUI();
}

function toggleSelectAllVideos(checked) {
    currentDirItems.forEach(item => {
        if (!item.is_dir && isVideoFile(item.name)) {
            const fullPath = '/media/' + item.path.replace(/\\/g, '/');
            if (checked) {
                selectedFiles.add(fullPath);
            } else {
                selectedFiles.delete(fullPath);
            }
        }
    });
    updateSelectionUI();
}

function updateSelectionUI() {
    const selectedArray = Array.from(selectedFiles);
    const input = document.getElementById('selected-path');
    if (input) {
        if (selectedArray.length === 0) {
            input.value = 'No file selected';
        } else if (selectedArray.length === 1) {
            input.value = selectedArray[0];
        } else {
            input.value = `${selectedArray.length} files selected`;
        }
    }
    
    const btn = document.getElementById('add-job-btn');
    if (btn) {
        btn.disabled = selectedArray.length === 0;
        if (btn.disabled) btn.classList.remove('btn-primary');
        else btn.classList.add('btn-primary');
    }

    // Refresh browser items icons
    document.querySelectorAll('.browser-item').forEach(item => {
        const selectionDiv = item.querySelector('.selection-icon');
        if (selectionDiv) {
            const onclickStr = selectionDiv.getAttribute('onclick');
            const match = onclickStr.match(/toggleFileSelection\('(.*)'\)/);
            if (match) {
                const path = match[1];
                const isSelected = selectedFiles.has(path);
                item.classList.toggle('selected', isSelected);
                selectionDiv.innerHTML = `<i data-lucide="${isSelected ? 'square-check' : 'square'}"></i>`;
            }
        }
    });

    // Update select all icon
    const selectAllDiv = document.querySelector('.selection-icon.select-all');
    if (selectAllDiv) {
        const hasVideos = currentDirItems.some(item => !item.is_dir && isVideoFile(item.name));
        const allSelected = hasVideos && currentDirItems
            .filter(item => !item.is_dir && isVideoFile(item.name))
            .every(item => selectedFiles.has('/media/' + item.path.replace(/\\/g, '/')));
        
        selectAllDiv.setAttribute('onclick', `toggleSelectAllVideos(!${allSelected})`);
        selectAllDiv.innerHTML = `<i data-lucide="${allSelected ? 'square-check' : 'square'}"></i>`;
    }
    
    lucide.createIcons();
}

function selectFile(path) {
    // Legacy function, might be used elsewhere or as fallback
    selectedFiles.clear();
    selectedFiles.add('/media/' + path);
    updateSelectionUI();
}

let lastMediaVersion = -1;

async function checkMediaChanges() {
    const createTab = document.getElementById('create');
    if (!createTab || !createTab.classList.contains('active')) return;
    
    try {
        const res = await fetch('/api/files/version');
        const data = await res.json();
        if (lastMediaVersion === -1) {
            lastMediaVersion = data.version;
        } else if (data.version !== lastMediaVersion) {
            lastMediaVersion = data.version;
            browse(currentBrowserPath);
        }
    } catch (e) {}
}

setInterval(checkMediaChanges, 2000);
