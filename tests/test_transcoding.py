import pytest
from playwright.sync_api import Page, expect
import time

def test_basic_transcoding(page: Page, server_url: str):
    """Test basic video transcoding flow."""
    page.goto(f"{server_url}/create-job")
    
    # Sync media just in case
    page.click('button[title="Rescan media directory"]')
    page.wait_for_selector('text="standard_test.mp4"')
    
    # Select standard test video
    page.click('text="standard_test.mp4"')
    
    # Wait for the right pane to populate with config for this file
    expect(page.locator('h4:has-text("Preset Overrides")')).to_be_visible()
    
    # Select H264 profile
    page.select_option('select[name="category"]', 'Default')
    page.select_option('select[name="preset"]', 'H264 1080p Fast')
    
    # Ensure button is enabled and click Start Transcode
    start_btn = page.locator('#job-submit-btn')
    expect(start_btn).to_be_enabled()
    start_btn.click()
    
    # The app should redirect to /jobs automatically after successful creation
    expect(page).to_have_url(f"{server_url}/jobs")
    
    # Go to Transcode History tab (since it will finish very quickly)
    page.click('text=Transcode History')
    
    # Look for our standard_test.mp4 in the history table and wait for status to be "completed"
    # Because it's a 2-second video with ultrafast, it will transcode in <1 second
    
    # We will poll/reload the page if needed, but HTMX polls automatically in active jobs. 
    # History tab might need refresh or maybe it just appears.
    # Actually, the active jobs tab polls. So let's check active jobs, wait for it to disappear, then check history.
    page.click('text=Active Transcodes')
    
    # Wait for the queue to be empty (either it never shows up because it finished instantly, or it finishes quickly)
    page.wait_for_timeout(2000)
    
    page.click('text=Transcode History')
    
    # The history item contains the input filename
    history_item = page.locator('tr:has-text("standard_test.mp4")')
    expect(history_item).to_be_visible(timeout=10000)
    
    # Assert status is completed
    expect(history_item).to_contain_text("COMPLETED")
