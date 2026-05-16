let settingsProfileTree = [];

async function loadSettings() {
    // Populate categories first
    const profileRes = await fetch('/api/profiles');
    const profileData = await profileRes.json();
    settingsProfileTree = profileData.tree;
    
    const catSelect = document.getElementById('setting-default_category');
    if (catSelect) {
        catSelect.innerHTML = '<option value="">None</option>' + 
            settingsProfileTree.map(node => `<option value="${node.name}">${node.name}</option>`).join('');
    }

    const res = await fetch('/api/settings');
    const data = await res.json();
    
    if (data.output_dir !== undefined) {
        document.getElementById('setting-output_dir').value = data.output_dir;
    }

    if (data.default_profile && catSelect) {
        // Find which category this profile belongs to
        const cat = settingsProfileTree.find(c => c.children && c.children.some(p => p.path === data.default_profile));
        if (cat) {
            catSelect.value = cat.name;
            updateSettingsProfileDropdown(data.default_profile);
        }
    } else {
        updateSettingsProfileDropdown();
    }
}

function updateSettingsProfileDropdown(forcePath = null) {
    const catSelect = document.getElementById('setting-default_category');
    const profSelect = document.getElementById('setting-default_profile');
    if (!catSelect || !profSelect) return;

    const catName = catSelect.value;
    const catNode = settingsProfileTree.find(n => n.name === catName);
    
    if (catNode && catNode.children) {
        profSelect.innerHTML = '<option value="">None</option>' + 
            catNode.children
                .filter(c => c.type === 'file')
                .map(c => `<option value="${c.path}">${c.name.replace(/\.(ebrake|toml)$/, '')}</option>`).join('');
        
        if (forcePath) profSelect.value = forcePath;
    } else {
        profSelect.innerHTML = '<option value="">None</option>';
    }
}

async function saveSettings() {
    const output_dir = document.getElementById('setting-output_dir').value;
    const default_profile = document.getElementById('setting-default_profile').value;
    
    const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir, default_profile })
    });
    const result = await res.json();
    if (result.success) {
        const btn = document.getElementById('save-settings-btn');
        const oldText = btn.innerText;
        btn.innerText = 'Settings Saved!';
        btn.style.background = '#10b981';
        setTimeout(() => {
            btn.innerText = oldText;
            btn.style.background = '';
        }, 2000);
    }
}
