from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from query_engine import parse_query
from scraper import scrape_deals
import os

app = FastAPI(title="MOJ Real Estate AI Extractor")

class QueryRequest(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "MOJ Real Estate Extractor is running. Use POST /extract to get data."}

@app.post("/extract")
async def extract_data(request: QueryRequest):
    """
    Endpoint to extract real estate data based on natural language query.
    """
    try:
        # 1. Parse the natural language query into filters
        filters = parse_query(request.query)
        print(f"Parsed Filters: {filters}")
        
        if not filters:
            raise HTTPException(status_code=400, detail="Could not understand the query.")
            
        # 2. Scrape data using Playwright
        result = await scrape_deals(filters)
        
        return {
            "query": request.query,
            "interpreted_filters": filters,
            "result": result
        }
        
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
