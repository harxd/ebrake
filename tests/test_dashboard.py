import pytest
from playwright.sync_api import Page, expect

def test_dashboard_load(page: Page, server_url: str):
    """Verify the dashboard loads properly."""
    page.goto(f"{server_url}/create-job")
    
    # Assert title
    expect(page).to_have_title("ebrake - High Performance Transcoding")
    
    # Assert main UI elements are present
    expect(page.locator("text=Media Library")).to_be_visible()
    expect(page.locator("text=Transcode Queue")).to_be_visible()
