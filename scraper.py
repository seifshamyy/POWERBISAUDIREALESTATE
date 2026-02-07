import asyncio
import base64
from playwright.async_api import async_playwright

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

# Original coordinates were calibrated for 1280x800 viewport
ORIGINAL_VIEWPORT = {"width": 1280, "height": 800}

async def scrape_deals(filters: dict):
    """
    Scrapes real estate deal details from the MOJ PowerBI report based on provided filters.
    """
    debug_info = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use ORIGINAL viewport to match the coordinate calibration
        context = await browser.new_context(viewport=ORIGINAL_VIEWPORT)
        page = await context.new_page()
        
        try:
            debug_info.append("Step 1: Navigating to PowerBI...")
            await page.goto(POWERBI_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for report content to load
            await page.wait_for_selector("div.visual", timeout=60000)
            debug_info.append("Step 2: Report loaded.")
            
            # Wait extra time for all animations to settle
            await page.wait_for_timeout(5000)
            
            # CRITICAL STEP: Switch to "Details" View
            # Use JavaScript to find all navigation elements
            debug_info.append("Step 3: Attempting to find navigation elements...")
            
            # Try multiple strategies
            switched = False
            
            # Strategy 1: Find button by aria-label containing "التفاصيل" or "Details"
            nav_buttons = await page.evaluate('''() => {
                const buttons = document.querySelectorAll('[role="button"], button, [tabindex="0"]');
                return Array.from(buttons).map(b => ({
                    text: b.innerText || b.textContent,
                    ariaLabel: b.getAttribute('aria-label'),
                    className: b.className,
                    tagName: b.tagName
                })).slice(0, 30);
            }''')
            debug_info.append(f"Found {len(nav_buttons)} potential buttons")
            
            # Strategy 2: Click on the right sidebar area (4th icon)
            # Original subagent coordinates: (975, 350) for 1280x800
            if not switched:
                debug_info.append("Step 4: Clicking sidebar at (975, 350)...")
                await page.mouse.click(975, 350)
                await page.wait_for_timeout(5000)
                
                # Check if we're on a different view by looking for table elements
                table_check = await page.evaluate('''() => {
                    const tables = document.querySelectorAll('[role="grid"], [role="table"], .tableEx');
                    return tables.length;
                }''')
                debug_info.append(f"Tables after click: {table_check}")
                
                if table_check > 0:
                    switched = True
                    debug_info.append("Successfully switched to table view!")
            
            # Strategy 3: Try keyboard navigation if click didn't work
            if not switched:
                debug_info.append("Step 5: Trying keyboard navigation...")
                # Tab through the page to find navigation
                for i in range(10):
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(200)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
            
            # Take a screenshot after navigation attempt
            screenshot_after_nav = await page.screenshot(type='jpeg', quality=50)
            
            # Apply Date Filters
            if filters.get("start_date") and filters.get("end_date"):
                debug_info.append(f"Step 6: Applying date filters: {filters['start_date']} - {filters['end_date']}")
                await apply_date_filter(page, filters["start_date"], filters["end_date"])
                await page.wait_for_timeout(8000)
            
            # Wait for data to load
            await page.wait_for_timeout(3000)
            
            # Data Extraction - Try multiple approaches
            debug_info.append("Step 7: Extracting data...")
            
            # Approach 1: Look for grid cells
            grid_cells = await page.evaluate('''() => {
                const cells = document.querySelectorAll('[role="gridcell"], [role="cell"], [role="rowheader"]');
                return Array.from(cells).map(c => c.innerText).filter(t => t && t.trim());
            }''')
            
            if grid_cells and len(grid_cells) > 10:
                debug_info.append(f"Found {len(grid_cells)} grid cells!")
                # Take final screenshot
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                return {
                    "data": "\n".join(grid_cells[:500]),
                    "status": "success",
                    "count": len(grid_cells),
                    "debug": debug_info,
                    "screenshot": screenshot_b64
                }
            
            # Approach 2: Get all text from the page body
            debug_info.append("Approach 2: Extracting all page text...")
            all_text = await page.evaluate('''() => {
                // Get text from the main content area
                const content = document.querySelector('.visualContainerHost') || document.body;
                return content.innerText;
            }''')
            
            # Take final screenshot
            screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # Filter and clean the text
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]
            
            # Apply city filter if specified
            city_filter = filters.get("city")
            if city_filter:
                filtered = [line for line in lines if city_filter in line]
                if filtered:
                    lines = filtered
            
            return {
                "data": "\n".join(lines[:500]),
                "status": "partial_success",
                "count": len(lines),
                "debug": debug_info,
                "screenshot": screenshot_b64
            }
                
        except Exception as e:
            debug_info.append(f"ERROR: {str(e)}")
            try:
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            except:
                screenshot_b64 = None
                
            return {
                "status": "error", 
                "message": str(e), 
                "debug": debug_info,
                "screenshot": screenshot_b64
            }
        finally:
            await browser.close()

async def apply_date_filter(page, start_date, end_date):
    """
    Applies the date filter using coordinates calibrated for 1280x800 viewport.
    Original subagent coordinates: Start Date at (66, 68), End Date at (161, 68)
    """
    try:
        # Start Date
        await page.mouse.click(66, 68)
        await page.wait_for_timeout(500)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(start_date, delay=50)
        await page.keyboard.press("Enter")
        
        await page.wait_for_timeout(1500)
        
        # End Date
        await page.mouse.click(161, 68)
        await page.wait_for_timeout(500)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(end_date, delay=50)
        await page.keyboard.press("Enter")
        
        print("Date filters applied via coordinates.")
        
    except Exception as e:
        print(f"Failed to apply date filters: {e}")

if __name__ == "__main__":
    asyncio.run(scrape_deals({"start_date": "01/01/2026", "end_date": "01/31/2026"}))
