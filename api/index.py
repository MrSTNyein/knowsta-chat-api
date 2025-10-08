import os
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from supabase import create_client, Client
from typing import Optional, List

# --- 1. Supabase and API Key Setup ---
# IMPORTANT: These secrets must be set in Vercel Environment Variables.

# Supabase Keys (for database connection)
SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY: Optional[str] = os.environ.get("SUPABASE_ANON_KEY")

# Custom API Key (for service access authentication)
API_ACCESS_KEY: Optional[str] = os.environ.get("API_ACCESS_KEY")

supabase: Optional[Client] = None
keys_loaded: bool = False

# Initialize the Supabase Client if keys are available
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        # Initialize client, which uses the PostgREST API under the hood
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        keys_loaded = True
    except Exception as e:
        # Log the failure but don't crash the serverless function cold start
        print(f"Failed to create Supabase client during startup: {e}")
        supabase = None

# --- 2. FastAPI Setup and Data Model ---
app = FastAPI(title="Knowsta Chat API")

# Pydantic Model for a new message (used for input validation)
class Message(BaseModel):
    user_id: str
    content: str

# Pydantic Model for the response data structure
class MessageResponse(BaseModel):
    id: str
    user_id: str
    content: str
    created_at: str

# --- API Key Authentication Dependency ---
def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-KEY")):
    """
    Dependency that checks the 'X-API-KEY' header against the secret key.
    """
    # Keys must be loaded AND the submitted key must match the secret
    if not keys_loaded or x_api_key is None or x_api_key != API_ACCESS_KEY:
        # If the key is missing or incorrect, deny access
        raise HTTPException(
            status_code=401, 
            detail="Unauthorized: Invalid or missing X-API-KEY header or server secrets not loaded."
        )
    return x_api_key

# --- 3. API Routes (Protected by API Key) ---

@app.get("/", tags=["Healthcheck"])
def root():
    """
    Simple health check endpoint to verify the API is running and check key status.
    If 'supabase_keys_loaded' is false, you must check your Vercel Environment Variables.
    """
    return {
        "status": "ok", 
        "service": "Knowsta Chat Python API",
        "supabase_keys_loaded": keys_loaded
    }

@app.post("/messages", response_model=MessageResponse, tags=["Messages"])
def send_message(
    message: Message, 
    authenticated_key: str = Depends(verify_api_key) # API Key Protection
):
    """
    Endpoint to insert a new message into the Supabase 'messages' table.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection error. Check Vercel logs for key errors.")
        
    try:
        # Insert data into the 'messages' table, relying on Supabase/Postgres 
        # to auto-generate 'id' and 'created_at'
        result = supabase.table('messages').insert({
            "user_id": message.user_id,
            "content": message.content,
        }).execute()

        # result.data will contain the successfully inserted record(s)
        # We assume one record is inserted
        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            return result.data[0]
        else:
             raise Exception("Supabase insert returned no data.")

    except Exception as e:
        print(f"Error inserting message: {e}")
        raise HTTPException(status_code=500, detail="Failed to insert message into database.")

@app.get("/messages", response_model=List[MessageResponse], tags=["Messages"])
def get_messages(
    authenticated_key: str = Depends(verify_api_key) # API Key Protection
):
    """
    Endpoint to retrieve the latest 50 messages from the 'messages' table.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection error. Check Vercel logs for key errors.")
        
    try:
        # Query the 'messages' table, order by creation time descending (latest first)
        # and limit the results to 50
        result = supabase.table('messages').select("*").order("created_at", desc=True).limit(50).execute()
        
        # result.data contains the fetched messages
        messages = result.data

        # We reverse the order to display oldest first, as is standard in chat logs.
        return messages[::-1] 

    except Exception as e:
        print(f"Error fetching messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages from database.")
