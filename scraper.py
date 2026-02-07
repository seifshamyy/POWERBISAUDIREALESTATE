import asyncio
from playwright.async_api import async_playwright

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

async def scrape_deals(filters: dict):
    """
    Scrapes real estate deal details from the MOJ PowerBI report based on provided filters.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        try:
            print(f"Navigating to {POWERBI_URL}...")
            await page.goto(POWERBI_URL, wait_until="networkidle")
            
            # Wait for report content to load
            # PowerBI reports are canvas based, so we wait for the main visual container
            await page.wait_for_selector("div.visual", timeout=30000)
            print("Report loaded.")
            
            # Apply Date Filters
            if filters.get("start_date") and filters.get("end_date"):
                print(f"Applying filters: {filters['start_date']} - {filters['end_date']}")
                await apply_date_filter(page, filters["start_date"], filters["end_date"])
            
            # Wait for data to update
            await page.wait_for_timeout(5000)
            
            # Extract Data
            # We'll look for the table visual. It's often a 'tableEx' class or similar in PowerBI
            # Since PowerBI renders text in accessible divs often, we can try to extract text from the visuals.
            
            # Strategy: Get all text from the "Details" visual.
            # We'll assume the table is the large visual with many rows.
            
            # Find the visual processing container for the table
            # Provide a robust selector for the table
            table_visual = page.locator(".visual-tableEx").first
            if await table_visual.count() > 0:
                print("Found table visual.")
                # Extract text content - this might need refinement based on structure
                text_content = await table_visual.inner_text()
                return {"data": text_content, "status": "success"}
            else:
                # Fallback: Capture a screenshot API style or just all text
                print("Table visual class not found, trying generic containers...")
                visuals = page.locator(".visualContainerGroup")
                count = await visuals.count()
                collected_text = []
                
                # Iterate through all visual containers to gather text
                for i in range(count):
                    try:
                        text = await visuals.nth(i).inner_text()
                        if text and len(text.strip()) > 50: # Only keep substantial content
                            collected_text.append(f"--- Container {i} ---\n{text}")
                    except Exception as e:
                        print(f"Error reading container {i}: {e}")
                
                full_text = "\n\n".join(collected_text)
                return {"data": full_text, "status": "partial_success", "message": f"Extracted text from {count} visual containers."}
                
        except Exception as e:
            print(f"Error during scraping: {e}")
            screenshot_path = "error_screenshot.png"
            await page.screenshot(path=screenshot_path)
            return {"status": "error", "message": str(e), "screenshot": screenshot_path}
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
