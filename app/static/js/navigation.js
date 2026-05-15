function tab(id, pushState = true) {
    document.querySelectorAll('.tab-content, .tab-header').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.nav button').forEach(el => el.classList.remove('active'));
    
    const content = document.getElementById(id);
    if (content) {
        content.style.display = (id === 'jobs' || id === 'profiles') ? 'flex' : 'block';
        content.classList.add('active');
    }
    
    const header = document.getElementById(id + '-header');
    if (header) header.style.display = 'block';
    
    const btn = Array.from(document.querySelectorAll('.nav button')).find(b => b.getAttribute('onclick').includes(`'${id}'`));
    if (btn) btn.classList.add('active');

    if (id === 'create') initJobPresets();
    if (id === 'jobs') fetchJobs();
    if (id === 'profiles') loadProfiles();
    if (id === 'settings') loadSettings();

    if (pushState && tabMap[id]) {
        history.pushState({ tabId: id }, '', tabMap[id]);
    }
}

window.onpopstate = function(event) {
    if (event.state && event.state.tabId) {
        tab(event.state.tabId, false);
    } else {
        initFromPath();
    }
};

function initFromPath() {
    const path = window.location.pathname;
    const tabId = Object.keys(tabMap).find(key => tabMap[key] === path) || 'create';
    tab(tabId, false);
}
