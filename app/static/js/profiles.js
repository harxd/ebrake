let profileDataTree = [];
let currentProfilePath = '';

async function initJobPresets() {
    const res = await fetch('/api/profiles');
    const data = await res.json();
    profileDataTree = data.tree;
    
    const catSelect = document.getElementById('job-category');
    if (catSelect) {
        catSelect.innerHTML = profileDataTree.map(node => `<option value="${node.name}">${node.name}</option>`).join('');
        updateJobPresetDropdown();
    }
}

function updateJobPresetDropdown() {
    const catSelect = document.getElementById('job-category');
    if (!catSelect) return;
    const catName = catSelect.value;
    const catNode = profileDataTree.find(n => n.name === catName);
    const presetSelect = document.getElementById('job-preset');
    if (catNode && catNode.children) {
        presetSelect.innerHTML = catNode.children
            .filter(c => c.type === 'file')
            .map(c => `<option value="${c.path}">${c.name.replace(/\.(ebrake|toml)$/, '')}</option>`).join('');
    } else {
        presetSelect.innerHTML = '';
    }
    loadJobPresetSettings();
}

async function loadJobPresetSettings() {
    const presetSelect = document.getElementById('job-preset');
    if (!presetSelect) return;
    const path = presetSelect.value;
    if (!path) return;

    const res = await fetch(`/api/profiles/read?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (data.error) return;

    const config = parseTOML(data.content);
    const fields = [
        'output_suffix', 'output_container', 
        'video_codec', 'video_preset', 'video_crf', 'video_tune', 'video_pix_fmt', 'video_fps_mode',
        'audio_passthrough_codecs', 'audio_fallback_codec', 'audio_fallback_bitrate'
    ];
    
    fields.forEach(f => {
        const el = document.getElementById(`job-field-${f}`);
        if (!el || config[f] === undefined) return;
        
        if (f === 'audio_passthrough_codecs') {
            const activeCodecs = config[f].split(',').map(s => s.trim());
            el.querySelectorAll('.toggle-btn').forEach(btn => {
                const codec = btn.innerText;
                btn.classList.toggle('active', activeCodecs.includes(codec));
            });
        } else if (f === 'video_preset') {
            updatePresetSlider('job-field', config[f]);
        } else {
            el.value = config[f];
            if (f === 'video_codec') updatePresetSlider('job-field');
        }
    });
}

async function loadProfiles() {
    const res = await fetch('/api/profiles');
    const data = await res.json();
    const container = document.getElementById('profile-tree');
    if (container) {
        container.innerHTML = `<div class="tree">${renderProfileTree(data.tree)}</div>`;
        lucide.createIcons();
        
        if (currentProfilePath) {
            const name = currentProfilePath.split('/').pop().replace(/\.(ebrake|toml)$/, '');
            // Restore active class without necessarily re-fetching everything immediately, 
            // but selectProfile is the most robust way.
            selectProfile(currentProfilePath, name);
        }
    }
}

function renderProfileTree(nodes, parentPath = '') {
    return nodes.map(node => {
        const fullPath = parentPath ? `${parentPath}/${node.name}` : node.name;
        if (node.type === 'dir') {
            const ctxItems = [
                { label: 'Add Category', icon: 'folder-plus', onclick: `promptCreateDir('${fullPath}')` },
                { label: 'Add Profile', icon: 'file-plus', onclick: `promptCreateFile('${fullPath}')` },
                { label: 'Delete Category', icon: 'trash-2', onclick: `deletePath('${fullPath}')` }
            ];
            return `
                <div class="tree-node" 
                     ondragover="handleProfileDragOver(event)" 
                     ondragleave="handleProfileDragLeave(event)" 
                     ondrop="handleProfileDrop(event, '${fullPath}')">
                    <div class="tree-item dir" 
                         onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'"
                         oncontextmenu="showContextMenu(event, ${JSON.stringify(ctxItems).replace(/"/g, '&quot;')})">
                        <i data-lucide="folder"></i>
                        <span>${node.name}</span>
                    </div>
                    <div class="tree-children">
                        ${renderProfileTree(node.children, fullPath)}
                    </div>
                </div>
            `;
        } else {
            const parentDir = parentPath;
            const ctxItems = [
                { label: 'Add Category', icon: 'folder-plus', onclick: `promptCreateDir('${parentDir}')` },
                { label: 'Add Profile', icon: 'file-plus', onclick: `promptCreateFile('${parentDir}')` },
                { label: 'Delete Profile', icon: 'trash-2', onclick: `deletePath('${node.path}')` }
            ];
            const cleanName = node.name.replace(/\.(ebrake|toml)$/, '');
            return `
                <div class="tree-item file" 
                     draggable="true"
                     ondragstart="handleProfileDragStart(event, '${node.path}')"
                     onclick="selectProfile('${node.path}', '${cleanName}')" 
                     data-path="${node.path}"
                     oncontextmenu="showContextMenu(event, ${JSON.stringify(ctxItems).replace(/"/g, '&quot;')})">
                    <i data-lucide="file-text"></i>
                    <span>${cleanName}</span>
                </div>
            `;
        }
    }).join('');
}

async function selectProfile(path, name) {
    currentProfilePath = path;
    document.querySelectorAll('.tree-item.file').forEach(el => el.classList.remove('active'));
    const activeItem = document.querySelector(`.tree-item.file[data-path="${path}"]`);
    if (activeItem) activeItem.classList.add('active');

    document.getElementById('profile-details-empty').style.display = 'none';
    document.getElementById('profile-editor').style.display = 'flex';
    document.getElementById('profile-title').innerText = name;
    
    const res = await fetch(`/api/profiles/read?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    
    if (data.error) {
        alert(`Error loading profile: ${data.error}`);
        return;
    }

    const config = parseTOML(data.content);
    const fields = [
        'output_suffix', 'output_container', 
        'video_codec', 'video_preset', 'video_crf', 'video_tune', 'video_pix_fmt', 'video_fps_mode',
        'audio_passthrough_codecs', 'audio_fallback_codec', 'audio_fallback_bitrate'
    ];
    
    fields.forEach(f => {
        const el = document.getElementById(`field-${f}`);
        if (!el || config[f] === undefined) return;
        
        if (f === 'audio_passthrough_codecs') {
            const activeCodecs = config[f].split(',').map(s => s.trim());
            el.querySelectorAll('.toggle-btn').forEach(btn => {
                const codec = btn.innerText;
                btn.classList.toggle('active', activeCodecs.includes(codec));
            });
        } else if (f === 'video_preset') {
            updatePresetSlider('field', config[f]);
        } else {
            el.value = config[f];
            if (f === 'video_codec') updatePresetSlider('field');
        }
    });
}

function toggleCodec(btn, codec) {
    btn.classList.toggle('active');
}

async function promptCreateDir(parent) {
    const name = prompt('Category Name:');
    if (!name) return;
    const res = await fetch('/api/profiles/create-dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent, name })
    });
    if ((await res.json()).success) loadProfiles();
}

async function promptCreateFile(parent) {
    const name = prompt('Profile Name:');
    if (!name) return;
    const res = await fetch('/api/profiles/create-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent, name })
    });
    if ((await res.json()).success) loadProfiles();
}

async function deletePath(path) {
    if (!confirm(`Are you sure you want to delete ${path}?`)) return;
    const res = await fetch('/api/profiles/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
    });
    if ((await res.json()).success) {
        loadProfiles();
        document.getElementById('profile-editor').style.display = 'none';
        document.getElementById('profile-details-empty').style.display = 'flex';
    }
}

function handleProfileDragStart(e, path) {
    e.dataTransfer.setData('text/plain', path);
    e.dataTransfer.effectAllowed = 'move';
}

function handleProfileDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('drag-target');
}

function handleProfileDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-target');
}

async function handleProfileDrop(e, dest) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-target');
    
    const src = e.dataTransfer.getData('text/plain');
    if (!src || src === dest) return;

    const res = await fetch('/api/profiles/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ src, dest })
    });
    
    if ((await res.json()).success) {
        loadProfiles();
    }
}

async function saveProfile() {
    const path = document.querySelector('.tree-item.file.active')?.getAttribute('data-path');
    if (!path) return;

    const config = {};
    const fields = [
        'output_suffix', 'output_container', 
        'video_codec', 'video_preset', 'video_crf', 'video_tune', 'video_pix_fmt', 'video_fps_mode',
        'audio_fallback_codec', 'audio_fallback_bitrate'
    ];

    fields.forEach(f => {
        const el = document.getElementById(`field-${f}`);
        if (el) {
            if (f === 'video_preset') config[f] = getPresetValue('field');
            else config[f] = el.value;
        }
    });

    const activeCodecs = [];
    document.querySelectorAll('#field-audio_passthrough_codecs .toggle-btn.active').forEach(btn => {
        activeCodecs.push(btn.innerText);
    });
    config['audio_passthrough_codecs'] = activeCodecs.join(',');

    const res = await fetch('/api/profiles/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, config })
    });

    const result = await res.json();
    if (result.success) {
        const btn = document.querySelector('#profile-editor .btn');
        const originalText = btn.innerText;
        btn.innerText = 'Saved!';
        btn.style.background = '#10b981';
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.background = '';
        }, 2000);
    } else {
        alert('Error saving profile: ' + result.error);
    }
}
