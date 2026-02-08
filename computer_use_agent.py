"""
Computer Use Agent for MOJ PowerBI Extraction

This agent uses Anthropic's Claude with vision capabilities to navigate
the PowerBI report by taking screenshots and deciding actions dynamically.
"""

import os
import base64
import asyncio
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Page
import anthropic

POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

# System prompt for Claude
SYSTEM_PROMPT = """You are an AI agent controlling a web browser to extract real estate data from a Saudi Ministry of Justice PowerBI report.

The report is in Arabic. Key elements:
- Date filters at the top (التاريخ ميلادي = Gregorian Date)
- City/Region dropdown (المنطقة/المدينة)
- Summary cards showing: عدد الصفقات (Number of Deals), السعر بالريال السعودي (Price in SAR)
- A "Details" view (التفاصيل) accessible from the right sidebar - this shows a table with individual deals

Your task is to:
1. Apply the requested date filters
2. Apply any city/region filters if specified
3. Navigate to the Details (التفاصيل) view to see the data table
4. Extract the deal data from the table

For each step, analyze the screenshot and respond with a JSON object:
{
    "thinking": "Your analysis of the current screen state",
    "action": "click" | "type" | "scroll" | "wait" | "extract" | "done",
    "x": <x coordinate for click>,
    "y": <y coordinate for click>,
    "text": "<text to type if action is type>",
    "extracted_data": "<data if action is extract>",
    "message": "<status message>"
}

IMPORTANT:
- The viewport is 1280x800 pixels
- Always verify your actions worked by checking the next screenshot
- When typing dates, use format MM/DD/YYYY
- To select all text before typing, triple-click first
- The Details view icon is on the right sidebar (4th or 5th icon from top)
- When done extracting data, use action "done"
"""


class ComputerUseAgent:
    def __init__(self, anthropic_api_key: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.page: Optional[Page] = None
        self.browser = None
        self.context = None
        self.action_history = []
        self.max_steps = 25  # Safety limit
        
    async def take_screenshot(self) -> str:
        """Capture screenshot and return as base64."""
        screenshot_bytes = await self.page.screenshot(type='png')
        return base64.standard_b64encode(screenshot_bytes).decode('utf-8')
    
    def send_to_claude(self, screenshot_b64: str, task: str, step: int) -> dict:
        """Send screenshot to Claude and get next action."""
        
        # Build conversation history for context
        history_summary = "\n".join([
            f"Step {i+1}: {action.get('action', 'unknown')} - {action.get('message', '')}" 
            for i, action in enumerate(self.action_history[-5:])  # Last 5 actions
        ])
        
        user_message = f"""Current Task: {task}

Step: {step}/{self.max_steps}

Previous Actions:
{history_summary if history_summary else "None yet"}

Analyze this screenshot and provide the next action as JSON."""

        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": user_message
                        }
                    ]
                }
            ]
        )
        
        # Parse Claude's response
        response_text = response.content[0].text
        
        # Extract JSON from response (Claude might include extra text)
        import json
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                return {"action": "wait", "message": "Failed to parse response"}
        
        return {"action": "wait", "message": "No JSON in response"}
    
    async def execute_action(self, action: dict) -> bool:
        """Execute the action specified by Claude."""
        action_type = action.get("action", "wait")
        
        if action_type == "click":
            x = action.get("x", 0)
            y = action.get("y", 0)
            click_count = action.get("click_count", 1)
            await self.page.mouse.click(x, y, click_count=click_count)
            await self.page.wait_for_timeout(1500)
            return True
            
        elif action_type == "type":
            text = action.get("text", "")
            # Clear existing text first if specified
            if action.get("clear_first", False):
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.press("Backspace")
            await self.page.keyboard.type(text, delay=50)
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(2000)
            return True
            
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            amount = action.get("amount", 300)
            if direction == "down":
                await self.page.mouse.wheel(0, amount)
            else:
                await self.page.mouse.wheel(0, -amount)
            await self.page.wait_for_timeout(1000)
            return True
            
        elif action_type == "wait":
            await self.page.wait_for_timeout(3000)
            return True
            
        elif action_type == "extract":
            # Claude has extracted data, we'll capture it from the action
            return True
            
        elif action_type == "done":
            return False  # Signal to stop the loop
            
        return True
    
    async def run(self, user_query: str) -> dict:
        """Main agent loop."""
        result = {
            "status": "error",
            "data": None,
            "steps": [],
            "screenshot": None
        }
        
        async with async_playwright() as p:
            self.browser = await p.chromium.launch(headless=True)
            self.context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
            self.page = await self.context.new_page()
            
            try:
                # Navigate to PowerBI
                print(f"[Agent] Navigating to PowerBI...")
                await self.page.goto(POWERBI_URL, wait_until="networkidle", timeout=60000)
                await self.page.wait_for_timeout(8000)  # Wait for report to fully render
                
                # Build the task description
                today = datetime.now().strftime("%m/%d/%Y")
                task = f"""User request: "{user_query}"
Today's date: {today}

Navigate the PowerBI report to:
1. Set appropriate date filters based on the user's request
2. Apply any location filters if mentioned
3. Switch to the Details/Table view (التفاصيل) using the sidebar
4. Extract the deal data visible in the table

When you have extracted the data, respond with action "done" and include the data in "extracted_data"."""

                # Agent loop
                for step in range(1, self.max_steps + 1):
                    print(f"[Agent] Step {step}/{self.max_steps}")
                    
                    # Take screenshot
                    screenshot = await self.take_screenshot()
                    
                    # Get action from Claude
                    action = self.send_to_claude(screenshot, task, step)
                    print(f"[Agent] Action: {action.get('action')} - {action.get('message', '')}")
                    
                    # Record action
                    self.action_history.append(action)
                    result["steps"].append({
                        "step": step,
                        "action": action.get("action"),
                        "message": action.get("message"),
                        "thinking": action.get("thinking", "")[:200]  # Truncate thinking
                    })
                    
                    # Check for extracted data
                    if action.get("extracted_data"):
                        result["data"] = action["extracted_data"]
                    
                    # Execute action
                    should_continue = await self.execute_action(action)
                    
                    if not should_continue:
                        result["status"] = "success"
                        break
                
                # Capture final screenshot
                final_screenshot = await self.take_screenshot()
                result["screenshot"] = final_screenshot
                
                # If we hit max steps without completing
                if result["status"] != "success":
                    result["status"] = "partial"
                    result["message"] = f"Reached max steps ({self.max_steps})"
                    
                    # Try to extract any visible data as fallback
                    all_text = await self.page.evaluate('() => document.body.innerText')
                    if not result["data"]:
                        result["data"] = all_text[:5000]
                        
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
                print(f"[Agent] Error: {e}")
                
                try:
                    result["screenshot"] = await self.take_screenshot()
                except:
                    pass
                    
            finally:
                await self.browser.close()
        
        return result


async def test_agent():
    """Test the agent locally."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        return
    
    agent = ComputerUseAgent(api_key)
    result = await agent.run("Get real estate deals for the past week in Riyadh")
    
    print("\n=== Result ===")
    print(f"Status: {result['status']}")
    print(f"Steps taken: {len(result['steps'])}")
    for step in result['steps']:
        print(f"  {step['step']}: {step['action']} - {step['message']}")
    if result['data']:
        print(f"Data preview: {str(result['data'])[:500]}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_agent())
