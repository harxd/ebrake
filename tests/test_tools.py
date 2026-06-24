import pytest
from playwright.sync_api import Page, expect
from pathlib import Path

def test_dedup_tool(page: Page, server_url: str):
    """Test the FPS Deduplication dry-run tool."""
    page.goto(f"{server_url}/tools")
    
    # Click sync media just in case
    page.click('button[title="Rescan media directory"]')
    page.wait_for_selector('text="duplicates.mp4"')
    
    # Ensure Dedup tab is active
    page.click('button:has-text("FPS Deduplication")')
    
    # Find and click duplicates.mp4 in the file browser
    # The file browser might be a tree or list. We look for the file name text.
    page.click('text="duplicates.mp4"')
    
    # The run button should become enabled
    run_btn = page.locator('#tool-dedup-btn')
    expect(run_btn).to_be_enabled()
    
    run_btn.click()
    
    # Wait for result to appear
    result_box = page.locator('#dedup-result-container')
    expect(result_box.locator('text=Source FPS')).to_be_visible(timeout=15000)

def test_vmaf_compare_tool(page: Page, server_url: str):
    """Test the VMAF Comparison tool."""
    page.goto(f"{server_url}/tools")
    
    # Go to VMAF Compare tab
    page.click('button:has-text("VMAF Comparison")')
    
    # Select Reference Video
    page.click('#tool_file_path_field_compare_ref')
    page.click('text="standard_test.mp4"')
    
    # Select Distorted Video
    page.click('#tool_file_path_field_compare_dist')
    page.click('text="vmaf_distorted.mp4"')
    
    # Change mode to Segment to make it very fast
    page.select_option('select[name="compare_mode"]', 'segment')
    page.fill('input[name="duration"]', '1.0') # 1 second duration
    
    run_btn = page.locator('#tool-vmaf-compare-btn')
    expect(run_btn).to_be_enabled()
    
    run_btn.click()
    
    # Wait for result
    result_box = page.locator('#vmaf-compare-result-container')
    expect(result_box.locator('text=VMAF Score')).to_be_visible(timeout=30000)
