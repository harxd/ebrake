async function loadSettings() {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.output_dir !== undefined) {
        document.getElementById('setting-output_dir').value = data.output_dir;
    }
}

async function saveSettings() {
    const output_dir = document.getElementById('setting-output_dir').value;
    const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_dir })
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
