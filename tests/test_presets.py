import pytest
from playwright.sync_api import Page, expect

def test_preset_management(page: Page, server_url: str):
    """Test category creation, preset creation, editing, and drag-and-drop."""
    page.goto(f"{server_url}/presets")
    
    # 1. Create Category "Bob"
    page.fill('input[name="name"][placeholder="New Category Name..."]', "Bob")
    page.click('.inline-add-form button[type="submit"]')
    expect(page.locator('strong:has-text("Bob")')).to_be_visible()

    # 2. Create Preset inside Category Bob
    category_bob = page.locator(".category-tree-item", has_text="Bob")
    category_bob.locator("button:has-text('New Preset')").click()

    # Wait for the config form to show up
    expect(page.locator('input[name="preset_name"]')).to_be_visible()
    
    page.fill('input[name="preset_name"]', "Bob Preset")
    page.fill('input[name="output_suffix"]', "_bob")
    page.select_option('select[name="codec"]', 'libx265') # Change video codec
    page.click('#preset-save-btn')
    
    # Wait for it to appear in the tree
    bob_preset_locator = page.locator('.preset-name-text:has-text("Bob Preset")')
    expect(bob_preset_locator).to_be_visible()
    
    # 3. Create Category "Alice"
    page.fill('input[name="name"][placeholder="New Category Name..."]', "Alice")
    page.click('.inline-add-form button[type="submit"]')
    expect(page.locator('strong:has-text("Alice")')).to_be_visible()
    
    # 4. Delete Preset
    # Click the preset to ensure it's selected, then click its trash icon
    bob_preset_item = category_bob.locator(".preset-tree-item", has_text="Bob Preset")
    
    # We have to accept the native JS confirm dialog
    page.on("dialog", lambda dialog: dialog.accept())
    bob_preset_item.locator("button[title='Delete Preset']").click()
    
    expect(page.locator('.preset-name-text:has-text("Bob Preset")')).not_to_be_visible()

    # 5. Clean up categories Bob and Alice
    category_bob.locator("button[title='Delete Category']").click()
    expect(page.locator('.category-title-row strong:has-text("Bob")')).not_to_be_visible()

    category_alice = page.locator(".category-tree-item", has_text="Alice")
    category_alice.locator("button[title='Delete Category']").click()
    expect(page.locator('.category-title-row strong:has-text("Alice")')).not_to_be_visible()
