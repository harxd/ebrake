import pytest
from playwright.sync_api import Page, expect

def test_settings_persistence(page: Page, server_url: str):
    """Verify system settings can be modified and persist."""
    page.goto(f"{server_url}/settings")
    
    # Enable privacy mode
    page.click('text=Enable Privacy Mode')
    
    # Change startup recovery
    recovery_select = page.locator('select[name="recovery_action"]')
    recovery_select.select_option("auto_restart")
    
    # Save settings
    page.click('#settings-save-btn')
    
    # Wait a bit for HTMX response (or check toast, but let's just reload to be sure)
    page.wait_for_timeout(500)
    page.reload()
    
    # Assert persistence
    expect(page.locator('input[name="privacy_mode"]')).to_be_checked()
    expect(page.locator('select[name="recovery_action"]')).to_have_value("auto_restart")
