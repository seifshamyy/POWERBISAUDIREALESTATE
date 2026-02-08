"""
MOJ Real Estate Extractor API - Clean Rebuild
Uses Anthropic Claude with vision to navigate PowerBI.
"""
import os
import base64
import asyncio
import json
import re
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
import anthropic

# Constants
POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiNGI5OWM4NzctMDExNS00ZTBhLWIxMmYtNzIyMTJmYTM4MzNjIiwidCI6IjMwN2E1MzQyLWU1ZjgtNDZiNS1hMTBlLTBmYzVhMGIzZTRjYSIsImMiOjl9"

SYSTEM_PROMPT = """You are an AI agent controlling a browser to extract Saudi real estate data from a PowerBI report.

The report is in Arabic. Your task:
1. Apply date filters if requested
2. Navigate to the Details view (التفاصيل) - 4th icon on right sidebar
3. Extract visible deal data

Respond with JSON only:
{"action": "click", "x": 100, "y": 200, "message": "clicking date input"}
{"action": "type", "text": "01/31/2026", "message": "typing date"}
{"action": "done", "extracted_data": "the data you see", "message": "complete"}

Viewport: 1280x800. Use action "done" when finished."""

# FastAPI App
app = FastAPI(title="MOJ Extractor", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Request(BaseModel):
    query: str

class Response(BaseModel):
    query: str
    status: str
    data: Optional[str] = None
    steps: list = []
    message: Optional[str] = None

@app.get("/")
async def root():
    return {"service": "MOJ Extractor", "version": "3.0.0", "status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/extract")
async def extract(request: Request):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")
    
    try:
        result = await run_agent(api_key, request.query)
        return Response(
            query=request.query,
            status=result["status"],
            data=result.get("data"),
            steps=result.get("steps", []),
            message=result.get("message")
        )
    except Exception as e:
        raise HTTPException(500, str(e))

async def run_agent(api_key: str, user_query: str) -> dict:
    """Main agent loop."""
    client = anthropic.Anthropic(api_key=api_key)
    steps = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        try:
            await page.goto(POWERBI_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(8000)
            
            task = f"User request: {user_query}\nToday: {datetime.now().strftime('%m/%d/%Y')}"
            
            for step_num in range(1, 20):
                # Screenshot
                screenshot = base64.b64encode(await page.screenshot(type='png')).decode()
                
                # Ask Claude
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot}},
                            {"type": "text", "text": f"{SYSTEM_PROMPT}\n\nTask: {task}\nStep {step_num}/20. What next?"}
                        ]
                    }]
                )
                
                # Parse response
                text = response.content[0].text
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if not match:
                    steps.append({"step": step_num, "error": "no json"})
                    continue
                    
                action = json.loads(match.group())
                steps.append({"step": step_num, "action": action.get("action"), "message": action.get("message")})
                
                # Execute
                if action["action"] == "click":
                    await page.mouse.click(action["x"], action["y"])
                    await page.wait_for_timeout(2000)
                elif action["action"] == "type":
                    await page.keyboard.type(action["text"], delay=50)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(2000)
                elif action["action"] == "done":
                    await browser.close()
                    return {"status": "success", "data": action.get("extracted_data"), "steps": steps}
                elif action["action"] == "wait":
                    await page.wait_for_timeout(3000)
            
            # Max steps reached - extract anyway
            text = await page.evaluate("() => document.body.innerText")
            await browser.close()
            return {"status": "partial", "data": text[:5000], "steps": steps, "message": "max steps"}
            
        except Exception as e:
            await browser.close()
            return {"status": "error", "message": str(e), "steps": steps}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
