let jobsData = [];
let currentJobSubTab = 'pending';

const statusRank = {
    'cancelled': 0,
    'completed': 1,
    'failed': 2,
    'running': 3,
    'pending': 4
};

let sortCol = null;
let sortDir = 'asc';

function setJobSubTab(status) {
    currentJobSubTab = status;
    document.querySelectorAll('.sub-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('onclick').includes(`'${status}'`));
    });
    const clearBtn = document.querySelector('#clear-tab-btn span');
    if (clearBtn) clearBtn.innerText = `Clear ${status.charAt(0).toUpperCase() + status.slice(1)}`;
    renderTable();
}

async function clearCurrentTabJobs() {
    if (!confirm(`Are you sure you want to clear all ${currentJobSubTab} jobs?`)) return;
    const res = await fetch('/api/jobs/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: currentJobSubTab })
    });
    if ((await res.json()).success) {
        fetchJobs();
    }
}

async function fetchJobs() {
    try {
        const res = await fetch('/api/jobs');
        jobsData = await res.json();
        
        // Update counts
        const counts = { pending: 0, completed: 0, cancelled: 0, failed: 0 };
        jobsData.forEach(j => {
            if (counts[j.status] !== undefined) counts[j.status]++;
        });
        for (const s in counts) {
            const el = document.getElementById(`count-${s}`);
            if (el) el.innerText = counts[s];
        }

        renderTable();
        updateFooter();
    } catch (e) { console.error("Failed to fetch jobs:", e); }
}

function updateFooter() {
    const runningJob = jobsData.find(j => j.status === 'running');
    const fileName = document.getElementById('footer-filename');
    const percentage = document.getElementById('footer-percentage');
    const progressBar = document.getElementById('footer-progress-bar');
    const eta = document.getElementById('footer-eta');
    const elapsed = document.getElementById('footer-elapsed');

    if (runningJob) {
        fileName.innerText = runningJob.input_path.split('/').pop();
        percentage.innerText = Math.round(runningJob.progress) + '%';
        progressBar.style.width = runningJob.progress + '%';
        
        const start = new Date(runningJob.started_at + "Z");
        const now = new Date();
        const diffSec = Math.floor((now - start) / 1000);
        elapsed.innerText = formatTime(diffSec);

        if (runningJob.progress > 0) {
            const totalSec = (diffSec / runningJob.progress) * 100;
            const remainingSec = Math.max(0, totalSec - diffSec);
            eta.innerText = formatTime(remainingSec);
        } else {
            eta.innerText = '--:--:--';
        }
    } else {
        fileName.innerText = '---';
        percentage.innerText = '0%';
        progressBar.style.width = '0%';
        eta.innerText = '--:--:--';
        elapsed.innerText = '--:--:--';
    }
}

function toggleSort(colId) {
    if (colId === 'pos') {
        sortCol = null;
        renderTable();
        return;
    }

    if (sortCol === colId) {
        if (sortDir === 'asc') {
            sortDir = 'desc';
        } else {
            sortCol = null;
        }
    } else {
        sortCol = colId;
        sortDir = 'asc';
    }
    renderTable();
}

function renderTable() {
    const cols = document.getElementById('table-cols');
    const header = document.getElementById('table-header');
    const body = document.getElementById('jobs-body');
    const table = document.getElementById('jobs-table');
    if (!cols || !header || !body || !table) return;

    const visibleCols = allColumns.filter(c => {
        if (c.id === 'savings' && currentJobSubTab === 'pending') return false;
        if (c.id === 'created_at' && currentJobSubTab === 'pending') return true;
        return c.visible;
    });

    cols.innerHTML = visibleCols.map(col => `<col id="col-${col.id}" style="width: ${col.width}px;">`).join('');
    
    const totalWidth = visibleCols.reduce((sum, c) => sum + c.width, 0);
    table.style.width = totalWidth + 'px';

    header.innerHTML = visibleCols.map((col, index) => {
        const isSorted = sortCol === col.id;
        const icon = isSorted ? (sortDir === 'asc' ? '<i data-lucide="chevron-up" style="width:12px; height:12px;"></i>' : '<i data-lucide="chevron-down" style="width:12px; height:12px;"></i>') : '';
        return `
        <th style="position: relative;"
            draggable="true" ondragstart="handleDragStart(event, ${index})" ondragover="handleDragOver(event)" ondrop="handleDrop(event, ${index})"
            oncontextmenu="showHeaderMenu(event)" onclick="toggleSort('${col.id}')">
            <div style="display: flex; align-items: center; gap: 0.5rem; overflow: hidden; text-overflow: ellipsis;">
                <span>${col.label}</span>
                ${icon}
            </div>
            <div class="resizer" onmousedown="initResize(event, '${col.id}')"></div>
        </th>
        `;
    }).join('');

    const compare = (a, b, col, dir) => {
        let valA = a[col] || '';
        let valB = b[col] || '';
        if (col === 'status') {
            valA = statusRank[a.status];
            valB = statusRank[b.status];
        }
        if (valA < valB) return dir === 'asc' ? -1 : 1;
        if (valA > valB) return dir === 'asc' ? 1 : -1;
        return 0;
    };

    const defaultCompare = (a, b) => {
        if (a.created_at > b.created_at) return -1;
        if (a.created_at < b.created_at) return 1;
        return 0;
    };

    const filteredData = jobsData.filter(j => j.status === currentJobSubTab)
        .sort((a, b) => {
            if (sortCol) {
                const res = compare(a, b, sortCol, sortDir);
                return res !== 0 ? res : defaultCompare(a, b);
            }
            return defaultCompare(a, b);
        });

    body.innerHTML = filteredData.map((job, idx) => `
        <tr data-job-id="${job.id}">
            ${visibleCols.map(col => {
                if (col.id === 'pos') return `<td>${idx + 1}</td>`;
                if (col.id === 'status') return `<td><div class="status-pill status-${job.status}">${job.status}</div></td>`;
                if (col.id === 'filename') {
                    const fname = job.input_path.split('/').pop();
                    return `
                        <td>
                            <div style="font-weight: 600; color: white; margin-bottom: 0.25rem;">${fname}</div>
                            <div class="progress-container">
                                <div class="progress-bar" style="width: ${job.progress}%"></div>
                            </div>
                        </td>
                    `;
                }
                if (col.id === 'duration') {
                    if (!job.started_at) return `<td>--:--:--</td>`;
                    const start = new Date(job.started_at + (job.started_at.endsWith('Z') ? '' : 'Z'));
                    const end = job.finished_at ? new Date(job.finished_at + (job.finished_at.endsWith('Z') ? '' : 'Z')) : new Date();
                    const diffSec = Math.floor((end - start) / 1000);
                    return `<td>${formatTime(diffSec)}</td>`;
                }
                if (col.id === 'savings') return `<td>${job.savings}</td>`;
                return `<td>${job[col.id] || '-'}</td>`;
            }).join('')}
        </tr>
    `).join('');
    lucide.createIcons();
}

async function addToQueue() {
    const input_path = document.getElementById('selected-path').value;
    const profile_path = document.getElementById('job-preset').value;
    
    if (!input_path || input_path === 'No file selected') {
        alert('Please select a file first');
        return;
    }

    // Collect current UI configuration
    const config = {};
    const fields = [
        'output_suffix', 'output_container', 
        'video_codec', 'video_preset', 'video_crf', 'video_tune', 'video_pix_fmt', 'video_fps_mode',
        'audio_fallback_codec', 'audio_fallback_bitrate'
    ];

    fields.forEach(f => {
        const el = document.getElementById(`job-field-${f}`);
        if (el) {
            if (f === 'video_preset') config[f] = getPresetValue('job-field');
            else config[f] = el.value;
        }
    });

    const activeCodecs = [];
    document.querySelectorAll('#job-field-audio_passthrough_codecs .toggle-btn.active').forEach(btn => {
        activeCodecs.push(btn.innerText);
    });
    config['audio_passthrough_codecs'] = activeCodecs.join(',');

    const res = await fetch('/api/jobs/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_path, profile_path, config })
    });
    
    if ((await res.json()).success) {
        fetchJobs();
    }
}

// Auto-refresh jobs
setInterval(fetchJobs, 2000);
