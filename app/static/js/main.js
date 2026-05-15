document.addEventListener('DOMContentLoaded', () => { 
    lucide.createIcons(); 
    initFromPath();
    browse(''); 
    initJobPresets();
    fetchJobs();
    
    // Initial slider updates
    const jobCodec = document.getElementById('job-field-video_codec');
    if (jobCodec) updatePresetSlider('job-field');
    const fieldCodec = document.getElementById('field-video_codec');
    if (fieldCodec) updatePresetSlider('field');
});
