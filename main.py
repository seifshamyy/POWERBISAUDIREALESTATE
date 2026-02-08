"""
MOJ Real Estate Extractor API
Uses Anthropic Computer Use for vision-based browser automation.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from computer_use_agent import ComputerUseAgent

load_dotenv()

app = FastAPI(
    title="MOJ Real Estate Extractor",
    description="AI-powered extraction from Saudi MOJ PowerBI using Anthropic Computer Use",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractionRequest(BaseModel):
    query: str
    
    
class ExtractionResponse(BaseModel):
    query: str
    status: str
    data: Optional[str] = None
    steps: list = []
    message: Optional[str] = None
    screenshot: Optional[str] = None


@app.get("/")
async def root():
    return {
        "service": "MOJ Real Estate Extractor",
        "version": "2.0.0",
        "engine": "Anthropic Computer Use",
        "status": "operational"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/extract", response_model=ExtractionResponse)
async def extract_data(request: ExtractionRequest):
    """
    Extract real estate data based on natural language query.
    
    Examples:
    - "Get deals for the past week"
    - "Show me real estate transactions in Riyadh for January 2026"
    - "Extract commercial property deals for the last month"
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    
    try:
        agent = ComputerUseAgent(api_key)
        result = await agent.run(request.query)
        
        return ExtractionResponse(
            query=request.query,
            status=result.get("status", "unknown"),
            data=result.get("data"),
            steps=result.get("steps", []),
            message=result.get("message"),
            screenshot=result.get("screenshot")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
