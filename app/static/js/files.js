let currentBrowserPath = '';

async function browse(relPath) {
    currentBrowserPath = relPath;
    const res = await fetch(`/api/files?path=${encodeURIComponent(relPath)}`);
    const data = await res.json();
    
    if (data.error) {
        console.error(data.error);
        return;
    }

    renderBreadcrumbs(relPath);
    const browser = document.getElementById('file-browser');
    if (browser) {
        browser.innerHTML = data.items.map(item => `
            <div class="browser-item ${item.is_dir ? 'dir' : 'file'}" onclick="${item.is_dir ? `browse('${item.path.replace(/\\/g, '/')}')` : `selectFile('${item.path.replace(/\\/g, '/')}')`}">
                <i data-lucide="${item.is_dir ? 'folder' : 'file-video'}"></i>
                <span>${item.name}</span>
            </div>
        `).join('');
        lucide.createIcons();
    }
}

function renderBreadcrumbs(path) {
    const container = document.getElementById('breadcrumbs');
    if (!container) return;
    const parts = path.split('/').filter(p => p);
    let html = `<span class="breadcrumb-item" onclick="browse('')">/media</span>`;
    let current = '';
    parts.forEach((p, i) => {
        current += (i === 0 ? '' : '/') + p;
        html += ` <span class="breadcrumb-separator">/</span> <span class="breadcrumb-item" onclick="browse('${current}')">${p}</span>`;
    });
    container.innerHTML = html;
}

function selectFile(path) {
    document.querySelectorAll('.browser-item').forEach(el => el.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
    document.getElementById('selected-path').value = '/media/' + path;
    const btn = document.getElementById('add-job-btn');
    btn.disabled = false;
    btn.classList.add('btn-primary');
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
