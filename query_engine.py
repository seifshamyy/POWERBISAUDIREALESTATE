import os
import json
from datetime import date
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def parse_query(user_query: str) -> dict:
    """
    Parses a natural language query into structured filter parameters for the real estate report.
    """
    today = date.today().isoformat()
    
    system_prompt = f"""
    You are an intelligent assistant that extracts structured filters from natural language queries about real estate deals.
    The current date is {today}.
    
    The target system has the following filters:
    - Date Range (start_date, end_date) in MM/DD/YYYY format.
    - City (optional).
    - Category (optional, e.g., 'Residential', 'Commercial').
    
    Return a JSON object with the following keys:
    - start_date: string (MM/DD/YYYY) or null
    - end_date: string (MM/DD/YYYY) or null
    - city: string or null
    - category: string or null

    Example:
    Query: "Show me deals in Riyadh for the last week"
    Response: {{ "start_date": "02/01/2026", "end_date": "02/08/2026", "city": "Riyadh", "category": null }}
    
    If the user doesn't specify a date, default to the last 30 days.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error parsing query: {e}")
        # Fallback to default past 30 days if error
        return {
            "start_date": None, # Logic elsewhere will handle defaults if needed, but safe to return None
            "end_date": None,
            "city": None,
            "category": None
        }
