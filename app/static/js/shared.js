const allColumns = [
    { id: 'pos', label: '#', visible: true, width: 40 },
    { id: 'filename', label: 'File Name', visible: true, width: 300 },
    { id: 'status', label: 'status', visible: false, width: 120 },
    { id: 'duration', label: 'Duration', visible: true, width: 100 },
    { id: 'savings', label: 'Savings', visible: true, width: 100 },
    { id: 'created_at', label: 'Created At', visible: false, width: 150 },
    { id: 'updated_at', label: 'Updated At', visible: false, width: 150 },
    { id: 'started_at', label: 'Started At', visible: false, width: 150 },
    { id: 'finished_at', label: 'Finished At', visible: false, width: 150 },
    { id: 'input_path', label: 'Input Path', visible: false, width: 400 },
    { id: 'output_path', label: 'Output Path', visible: false, width: 400 },
    { id: 'preset', label: 'Preset', visible: false, width: 150 },
    { id: 'error', label: 'Error', visible: false, width: 300 },
    { id: 'command', label: 'FFmpeg Command', visible: false, width: 600 }
];

const tabMap = {
    'create': '/create',
    'jobs': '/jobs',
    'profiles': '/profiles',
    'settings': '/settings'
};

const x26xPresets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'];

function formatTime(sec) {
    if (isNaN(sec) || sec < 0) return '--:--:--';
    const h = Math.floor(sec / 3600).toString().padStart(2, '0');
    const m = Math.floor((sec % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function parseTOML(content) {
    const lines = content.split('\n');
    const config = {};
    let currentSection = '';

    lines.forEach(line => {
        line = line.trim();
        if (!line || line.startsWith('#')) return;
        const sectionMatch = line.match(/^\[(.*)\]$/);
        if (sectionMatch) { currentSection = sectionMatch[1]; return; }
        const match = line.match(/^([a-z0-9_]+)\s*=\s*"(.*)"/);
        if (match) { config[currentSection ? `${currentSection}_${match[1]}` : match[1]] = match[2]; }
        const matchNum = line.match(/^([a-z0-9_]+)\s*=\s*([0-9.]+)/);
        if (matchNum) { config[currentSection ? `${currentSection}_${match[1]}` : match[1]] = matchNum[2]; }
    });
    return config;
}
