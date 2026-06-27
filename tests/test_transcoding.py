import os
import pytest
from pathlib import Path
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
    
    # Select H264 preset
    page.select_option('select[name="category"]', 'Default')
    page.wait_for_selector('select[name="preset"] option[value="H264 1080p Fast"]', state="attached")
    page.select_option('select[name="preset"]', 'H264 1080p Fast')
    
    # Ensure button is enabled and click Start Transcode
    start_btn = page.locator('#job-submit-btn')
    expect(start_btn).to_be_enabled()
    start_btn.click()
    
    # The app should redirect to /jobs automatically after successful creation
    expect(page).to_have_url(f"{server_url}/jobs")
    
    # Go to Transcode History tab immediately
    page.click('text=Transcode History')
    
    # Look for our standard_test-1080p-fast.mp4 in the history table and wait for status to be "completed"
    history_item = page.locator('tr:has-text("standard_test-1080p-fast.mp4")')
    expect(history_item).to_be_visible(timeout=30000)
    
    # Assert status is completed
    expect(history_item).to_contain_text("COMPLETED")


def test_transcoding_with_info_file(page: Page, server_url: str):
    """Test video transcoding flow with save_info_file enabled."""
    page.goto(f"{server_url}/create-job")
    
    # Sync media just in case
    page.click('button[title="Rescan media directory"]')
    page.wait_for_selector('text="standard_test.mp4"')
    
    # Select standard test video
    page.click('text="standard_test.mp4"')
    
    # Wait for the right pane to populate with config for this file
    expect(page.locator('h4:has-text("Preset Overrides")')).to_be_visible()
    
    # Select H264 preset
    page.select_option('select[name="category"]', 'Default')
    page.wait_for_selector('select[name="preset"] option[value="H264 1080p Fast"]', state="attached")
    page.select_option('select[name="preset"]', 'H264 1080p Fast')
    
    # Check the "Save info.txt next to output file" checkbox by clicking its label text
    page.click('text="Save info.txt next to output file"')
    
    # Ensure button is enabled and click Start Transcode
    start_btn = page.locator('#job-submit-btn')
    expect(start_btn).to_be_enabled()
    start_btn.click()
    
    # The app should redirect to /jobs automatically after successful creation
    expect(page).to_have_url(f"{server_url}/jobs")
    
    # Go to Transcode History tab immediately
    page.click('text=Transcode History')
    
    history_item = page.locator('tr:has-text("standard_test-1080p-fast_1.mp4")')
    expect(history_item).to_be_visible(timeout=30000)
    expect(history_item).to_contain_text("COMPLETED")
    
    # Verify that the specific info file exists in the output directory
    media_dir = os.environ.get("EBRAKE_MEDIA_DIR")
    assert media_dir is not None
    info_path = Path(media_dir) / "standard_test-1080p-fast_1_info.txt"
    
    if not info_path.exists():
        import sqlite3
        sandbox_db_path = Path(os.environ["EBRAKE_APPDATA_DIR"]) / "db" / "ebrake.db"
        print(f"\n=== DEBUG: SANDBOX DB ON FAILURE ({sandbox_db_path}) ===")
        if sandbox_db_path.exists():
            conn = sqlite3.connect(str(sandbox_db_path))
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM jobs;")
            for row in cur.fetchall():
                print(dict(row))
            conn.close()
        else:
            print("Sandbox DB does not exist!")
        print("=== END DEBUG ===")
        
    assert info_path.exists(), f"info file was not created! expected at: {info_path}"
    
    # Read the info.txt and verify some contents
    content = info_path.read_text(encoding="utf-8")
    assert "ebrake Transcode Info" in content
    assert "Job ID:" in content
    assert "Codec:            libx264" in content
    assert "Status:         Completed" in content
