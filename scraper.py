import asyncio
import base64
from playwright.async_api import async_playwright

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

# Verified coordinates from browser inspection (for 1200x800 viewport)
COORDS = {
    "start_date": (69, 68),
    "end_date": (164, 68),
    "city_dropdown": (711, 148),
    "city_search": (722, 177),
    "city_first_checkbox": (660, 200),  # First checkbox after search
    "details_view": (976, 364),  # 4th sidebar icon
}

async def scrape_deals(filters: dict):
    """
    Scrapes real estate deal details from the MOJ PowerBI report.
    Uses CLICK + TYPE approach (proven to work in manual testing).
    """
    debug_info = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1200, "height": 800})
        page = await context.new_page()
        
        try:
            debug_info.append("Step 1: Navigating to PowerBI...")
            await page.goto(POWERBI_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for report to fully load
            await page.wait_for_selector("div.visual", timeout=60000)
            await page.wait_for_timeout(8000)  # Extra wait for PowerBI
            debug_info.append("Step 2: Report loaded.")
            
            # STEP 3: Apply Date Filters using CLICK + TYPE
            if filters.get("start_date") and filters.get("end_date"):
                debug_info.append(f"Step 3: Setting dates: {filters['start_date']} - {filters['end_date']}")
                
                # Click START DATE input
                await page.mouse.click(*COORDS["start_date"])
                await page.wait_for_timeout(500)
                
                # Triple-click to select all text in the input
                await page.mouse.click(*COORDS["start_date"], click_count=3)
                await page.wait_for_timeout(300)
                
                # Type the start date (format: M/D/YYYY to match PowerBI)
                start_date = filters["start_date"]
                await page.keyboard.type(start_date, delay=50)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(2000)
                debug_info.append(f"Start date entered: {start_date}")
                
                # Click END DATE input
                await page.mouse.click(*COORDS["end_date"])
                await page.wait_for_timeout(500)
                
                # Triple-click to select all
                await page.mouse.click(*COORDS["end_date"], click_count=3)
                await page.wait_for_timeout(300)
                
                # Type the end date
                end_date = filters["end_date"]
                await page.keyboard.type(end_date, delay=50)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
                debug_info.append(f"End date entered: {end_date}")
            
            # STEP 4: Apply City Filter (if specified)
            city_filter = filters.get("city")
            if city_filter:
                debug_info.append(f"Step 4: Selecting city: {city_filter}")
                
                # Open city dropdown
                await page.mouse.click(*COORDS["city_dropdown"])
                await page.wait_for_timeout(1500)
                
                # The dropdown should now be open - take a checkpoint screenshot
                debug_info.append("Dropdown opened")
                
                # Click the search box
                await page.mouse.click(*COORDS["city_search"])
                await page.wait_for_timeout(500)
                
                # Clear any existing text and type city name
                await page.keyboard.press("Control+A")
                await page.keyboard.type(city_filter, delay=100)
                await page.wait_for_timeout(2000)
                debug_info.append(f"Typed city: {city_filter}")
                
                # Click the first checkbox result (position varies, so we'll click in the result area)
                await page.mouse.click(*COORDS["city_first_checkbox"])
                await page.wait_for_timeout(1500)
                
                # Close dropdown by clicking elsewhere
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(2000)
                debug_info.append("City selected and dropdown closed")
            
            # Wait for filters to apply
            await page.wait_for_timeout(5000)
            
            # STEP 5: Take a screenshot BEFORE switching views to verify filters
            mid_screenshot = await page.screenshot(type='jpeg', quality=60)
            debug_info.append("Step 5: Captured mid-process screenshot")
            
            # STEP 6: Switch to Details View
            debug_info.append("Step 6: Switching to Details view...")
            await page.mouse.click(*COORDS["details_view"])
            await page.wait_for_timeout(6000)
            
            # STEP 7: Extract Data
            debug_info.append("Step 7: Extracting data...")
            
            # First, try to find actual table data
            table_data = await page.evaluate('''() => {
                // Look for the Details table which has specific class
                const cells = document.querySelectorAll('.bodyCells, .pivotTableCellWrap, [role="gridcell"]');
                if (cells.length > 0) {
                    return Array.from(cells).map(c => c.innerText).filter(t => t && t.trim()).slice(0, 500);
                }
                // Fallback: get all text
                return [];
            }''')
            
            if table_data and len(table_data) > 5:
                debug_info.append(f"Extracted {len(table_data)} table cells")
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                return {
                    "data": "\n".join(table_data),
                    "status": "success",
                    "count": len(table_data),
                    "debug": debug_info,
                    "screenshot": screenshot_b64
                }
            
            # Fallback: Get all visible text
            all_text = await page.evaluate('() => document.body.innerText')
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]
            
            screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
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

if __name__ == "__main__":
    result = asyncio.run(scrape_deals({
        "start_date": "1/1/2026", 
        "end_date": "1/31/2026",
        "city": None
    }))
    print(result["debug"])
    print(f"Status: {result['status']}")
    print(f"Data preview: {result.get('data', '')[:500]}")
