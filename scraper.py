import asyncio
import base64
from playwright.async_api import async_playwright

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

# Verified coordinates from browser inspection (for ~1200x800 viewport)
COORDS = {
    "start_date": (69, 68),
    "end_date": (164, 68),
    "city_dropdown": (711, 148),
    "city_search": (722, 177),
    "details_view": (976, 364),  # 4th sidebar icon
}

async def scrape_deals(filters: dict):
    """
    Scrapes real estate deal details from the MOJ PowerBI report.
    Uses verified coordinates and JavaScript for reliable filter application.
    """
    debug_info = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use viewport close to browser inspection size
        context = await browser.new_context(viewport={"width": 1200, "height": 800})
        page = await context.new_page()
        
        try:
            debug_info.append("Step 1: Navigating to PowerBI...")
            await page.goto(POWERBI_URL, wait_until="networkidle", timeout=60000)
            
            # Wait for report to fully load
            await page.wait_for_selector("div.visual", timeout=60000)
            await page.wait_for_timeout(5000)
            debug_info.append("Step 2: Report loaded.")
            
            # STEP 3: Apply Date Filters using JavaScript (most reliable)
            if filters.get("start_date") and filters.get("end_date"):
                debug_info.append(f"Step 3: Setting dates via JS: {filters['start_date']} - {filters['end_date']}")
                
                date_result = await page.evaluate(f'''(() => {{
                    const inputs = document.querySelectorAll('input.date-slicer-datepicker');
                    if (inputs.length >= 2) {{
                        // Clear and set start date
                        inputs[0].value = '{filters["start_date"]}';
                        inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        
                        // Clear and set end date
                        inputs[1].value = '{filters["end_date"]}';
                        inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inputs[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        
                        // Trigger update
                        inputs[1].dispatchEvent(new KeyboardEvent('keydown', {{ 
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true 
                        }}));
                        return 'success';
                    }}
                    return 'no_inputs_found';
                }})()''')
                
                debug_info.append(f"Date JS result: {date_result}")
                await page.wait_for_timeout(3000)
            
            # STEP 4: Apply City Filter (if specified)
            city_filter = filters.get("city")
            if city_filter:
                debug_info.append(f"Step 4: Selecting city: {city_filter}")
                
                # Open city dropdown
                await page.mouse.click(*COORDS["city_dropdown"])
                await page.wait_for_timeout(1000)
                
                # Click search box and type city name using clipboard (for Arabic support)
                await page.mouse.click(*COORDS["city_search"])
                await page.wait_for_timeout(500)
                
                # Use JavaScript to set the search value (handles Arabic)
                await page.evaluate(f'''(() => {{
                    const searchInput = document.querySelector('.searchInput input, input[placeholder*="Search"]');
                    if (searchInput) {{
                        searchInput.value = '{city_filter}';
                        searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }})()''')
                
                await page.wait_for_timeout(1500)
                
                # Click first checkbox result
                await page.mouse.click(732, 345)
                await page.wait_for_timeout(2000)
                
                # Close dropdown by clicking elsewhere
                await page.mouse.click(500, 300)
                await page.wait_for_timeout(1000)
                
                debug_info.append("City filter applied")
            
            # STEP 5: Switch to Details View
            debug_info.append("Step 5: Switching to Details view...")
            await page.mouse.click(*COORDS["details_view"])
            await page.wait_for_timeout(5000)
            
            # Verify we're in Details view by checking for table/grid
            table_check = await page.evaluate('''() => {
                const tables = document.querySelectorAll('.tableEx, [role="grid"], [role="table"]');
                return tables.length;
            }''')
            debug_info.append(f"Tables found: {table_check}")
            
            # Wait for data to load
            await page.wait_for_timeout(3000)
            
            # STEP 6: Extract Data
            debug_info.append("Step 6: Extracting data...")
            
            # Try to get grid cells first
            grid_data = await page.evaluate('''() => {
                const cells = document.querySelectorAll('[role="gridcell"], [role="cell"], [role="rowheader"]');
                return Array.from(cells).map(c => c.innerText).filter(t => t && t.trim());
            }''')
            
            if grid_data and len(grid_data) > 10:
                debug_info.append(f"Extracted {len(grid_data)} grid cells")
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                return {
                    "data": "\n".join(grid_data[:500]),
                    "status": "success",
                    "count": len(grid_data),
                    "debug": debug_info,
                    "screenshot": screenshot_b64
                }
            
            # Fallback: Extract all visible text
            all_text = await page.evaluate('''() => {
                return document.body.innerText;
            }''')
            
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
        "start_date": "01/01/2026", 
        "end_date": "01/31/2026",
        "city": None
    }))
    print(result)
