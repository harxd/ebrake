// ebrake Global Client-Side Interactions
console.log("ebrake client engine initialized successfully.");

// Helper for UI animations or logging if needed
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    // Show top-progress bar if needed during HTMX swaps
});

function flashSaveSuccess(btnId, originalTextHTML) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    
    // Save original HTML if not passed
    const originalHTML = originalTextHTML || btn.innerHTML;
    
    // Add success styling
    btn.classList.add('success-flash');
    btn.innerHTML = '<i class="fa-solid fa-check"></i> Saved!';
    btn.setAttribute('disabled', 'true');
    
    setTimeout(() => {
        btn.classList.remove('success-flash');
        btn.innerHTML = originalHTML;
        btn.setAttribute('disabled', 'true');
    }, 1500);
}
