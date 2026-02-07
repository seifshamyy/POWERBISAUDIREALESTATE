import asyncio
import base64
from playwright.async_api import async_playwright

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

async def scrape_deals(filters: dict):
    """
    Scrapes real estate deal details from the MOJ PowerBI report based on provided filters.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use full HD viewport to ensure sidebar layout matches desktop
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            print(f"Navigating to {POWERBI_URL}...")
            await page.goto(POWERBI_URL, wait_until="networkidle")
            
            # Wait for report content to load
            await page.wait_for_selector("div.visual", timeout=30000)
            print("Report loaded.")
            
            # CRITICAL STEP: Switch to "Details" View
            # Coordinate clicks are fragile. We try to find the text "التفاصيل" (Details) which is part of the navigator.
            try:
                print("Attempting to switch to 'Details' view via text locator...")
                # Look for the text specifically
                details_text = page.locator("text='التفاصيل'")
                if await details_text.count() > 0:
                    await details_text.first.click()
                    print("Clicked 'التفاصيل'.")
                    await page.wait_for_timeout(5000)
                else:
                    # Fallback to English
                    details_text_en = page.locator("text='Details'")
                    if await details_text_en.count() > 0:
                        await details_text_en.first.click()
                        print("Clicked 'Details'.")
                        await page.wait_for_timeout(5000)
                    else:
                        # Final Fallback to Coordinates (adjusted for 1920x1080 if needed, but original was 1280x800)
                        # We will try the original coordinate just in case, or a relative position
                        print("Text locator failed. Retrying coordinate click...")
                        await page.mouse.click(975, 350) 
                        await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Error switching view: {e}")

            # Apply Date Filters
            if filters.get("start_date") and filters.get("end_date"):
                print(f"Applying filters: {filters['start_date']} - {filters['end_date']}")
                await apply_date_filter(page, filters["start_date"], filters["end_date"])
                # Increased wait time for data reload
                await page.wait_for_timeout(8000)
            
            # Data Extraction Strategy
            # Target specific PowerBI grid/table roles
            grid_cells = page.locator("div[role='gridcell']")
            row_headers = page.locator("div[role='rowheader']")
            
            if await grid_cells.count() > 0 or await row_headers.count() > 0:
                print(f"Found {await grid_cells.count()} grid cells and {await row_headers.count()} row headers.")
                # Extract all text from the main accessible area
                # PowerBI often puts the main data in a specific container with aria-label containing "Data" or "Table"
                
                # We will try to extract line by line from the main visual container
                # and then post-process
                main_visuals = page.locator(".visualContainerGroup")
                count = await main_visuals.count()
                
                extracted_data = []
                
                for i in range(count):
                    # Get text and split by lines
                    text = await main_visuals.nth(i).inner_text()
                    lines = text.split('\n')
                    
                    # Heuristic: A data table container usually has many lines
                    if len(lines) > 5:
                        filtered_lines = [line for line in lines if line.strip()]
                        extracted_data.extend(filtered_lines)

                # Client-Side Filtering (Implementation of City/Category)
                # Since we can't easily drive the UI dropdowns, we filter the extracted text.
                # We look for lines containing the city name.
                
                final_results = []
                city_filter = filters.get("city")
                
                if city_filter:
                    print(f"Filtering results for city: {city_filter}")
                    # Simple inclusion check for now - assuming row data is on one line or adjacent
                    # This is imperfect but better than nothing for unstructured scrape
                    final_results = [line for line in extracted_data if city_filter in line]
                    
                    # If we found nothing specific, maybe return top rows (headers) + data
                    if not final_results:
                        final_results = extracted_data[:20] + ["... No specific city matches found in loaded view ..."]
                else:
                    final_results = extracted_data

                return {
                    "data": "\n".join(final_results[:500]), # Limit to avoid 502s on huge payloads
                    "status": "success", 
                    "count": len(final_results)
                }
            else:
                # Fallback to the generic container dump if no grid found
                print("No grid cells found, falling back to container dump...")
                visuals = page.locator(".visualContainerGroup")
                count = await visuals.count()
                collected_text = []
                
                for i in range(count):
                    text = await visuals.nth(i).inner_text()
                    if text and len(text.strip()) > 50:
                        collected_text.append(f"--- Container {i} ---\n{text}")
                
                full_text = "\n\n".join(collected_text)
                
                # Take a screenshot to show what happened
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                return {
                    "data": full_text, 
                    "status": "partial_success", 
                    "message": "Grid role not found, dumped containers.",
                    "screenshot": screenshot_b64
                }
                
        except Exception as e:
            print(f"Error during scraping: {e}")
            # Try to grab a screenshot even on error
            try:
                screenshot_bytes = await page.screenshot(type='jpeg', quality=50)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            except:
                screenshot_b64 = None
                
            return {"status": "error", "message": str(e), "screenshot": screenshot_b64}
        finally:
            await browser.close()

async def apply_date_filter(page, start_date, end_date):
    """
    Applies the date filter.
    Attempts to locate the date picker inputs.
    """
    # Attempt 1: Look for inputs by placeholder or class
    # PowerBI Date Slicers often have inputs with class 'date-slicer-control' or similar
    # Given the previous subagent success, we'll try to find inputs by type="text" in the top area
    
    inputs = page.locator("input.datepicker-input") # Generic guess, likely wrong class 
    
    # Attempt 2: Coordinate interaction based on known report layout (Fallback)
    # The subagent found: Start Date at (66, 68), End Date at (161, 68)
    # We will use this if explicit selectors fail, as it was proven to work.
    
    try:
        # Start Date
        await page.mouse.click(66, 68)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(start_date)
        await page.keyboard.press("Enter")
        
        await page.wait_for_timeout(1000)
        
        # End Date
        await page.mouse.click(161, 68)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(end_date)
        await page.keyboard.press("Enter")
        
        print("Date filters applied via coordinates.")
        
    except Exception as e:
        print(f"Failed to apply date filters: {e}")

if __name__ == "__main__":
    # Test run
    asyncio.run(scrape_deals({"start_date": "01/01/2026", "end_date": "01/31/2026"}))
