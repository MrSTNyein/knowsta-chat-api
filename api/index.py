import os
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from supabase import create_client, Client
from starlette.requests import Request
from starlette.responses import JSONResponse

# --- 1. Supabase and API Key Setup ---
# IMPORTANT: These secrets must be set in Vercel Environment Variables.

# Supabase Keys (for database connection)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Custom API Key (for service access authentication)
API_ACCESS_KEY = os.environ.get("API_ACCESS_KEY")

# Input Validation Checks - These checks happen when the function first loads
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    # In a serverless environment, this error will halt the cold start and log an issue.
    raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in Vercel environment variables.")
if not API_ACCESS_KEY:
    raise ValueError("API_ACCESS_KEY must be set in Vercel to protect the service endpoints.")

# Initialize the Supabase Client
try:
    # Initialize client, which uses the PostgREST API under the hood
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
except Exception as e:
    print(f"Failed to create Supabase client: {e}")
    supabase = None 

# --- 2. FastAPI Setup and Data Model ---
app = FastAPI(title="Knowsta Chat API")

# Pydantic Model for a new message (used for input validation)
class Message(BaseModel):
    user_id: str
    content: str

# --- API Key Authentication Dependency ---
def verify_api_key(x_api_key: str = Header(None, alias="X-API-KEY")):
    """
    Dependency that checks the 'X-API-KEY' header against the secret key.
    """
    if x_api_key is None or x_api_key != API_ACCESS_KEY:
        # If the key is missing or incorrect, deny access
        raise HTTPException(
            status_code=401, 
            detail="Unauthorized: Invalid or missing X-API-KEY header."
        )
    return x_api_key

# --- 3. API Routes (Protected by API Key) ---

@app.get("/", tags=["Healthcheck"])
async def root():
    """Simple health check endpoint to verify the API is running."""
    return {"status": "ok", "service": "Knowsta Chat Python API"}

@app.post("/messages", tags=["Messages"])
async def send_message(
    message: Message, 
    authenticated_key: str = Depends(verify_api_key) # API Key Protection
):
    """
    Endpoint to insert a new message into the Supabase 'messages' table.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection error.")
        
    try:
        # Insert data into the 'messages' table
        # We rely on Supabase/Postgres to auto-generate 'id' and 'created_at'
        data, count = supabase.table('messages').insert({
            "user_id": message.user_id,
            "content": message.content,
        }).execute()

        # data[1][0] contains the successfully inserted record
        return {"success": True, "message_data": data[1][0]}

    except Exception as e:
        print(f"Error inserting message: {e}")
        raise HTTPException(status_code=500, detail="Failed to insert message into database.")

@app.get("/messages", tags=["Messages"])
async def get_messages(
    authenticated_key: str = Depends(verify_api_key) # API Key Protection
):
    """
    Endpoint to retrieve the latest 50 messages from the 'messages' table.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection error.")
        
    try:
        # Query the 'messages' table, order by creation time descending (latest first)
        # and limit the results to 50
        data, count = supabase.table('messages').select("*").order("created_at", desc=True).limit(50).execute()
        
        # The Supabase client returns results in data[1].
        # We reverse the order (messages[::-1]) to display oldest first, as is standard in chat logs.
        messages = data[1]
        
        return messages[::-1] 

    except Exception as e:
        print(f"Error fetching messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages from database.")


# --- 4. Vercel Handler (Required for Vercel Python runtime) ---
# Vercel needs a handler function to dispatch requests to the FastAPI app.
async def handler(request: Request):
    """Vercel handler function to serve the FastAPI application."""
    # This uses the ASGI interface to handle the request with the FastAPI app
    return await app(request.scope, request.receive, lambda: JSONResponse({"status": "not found"}, 404))

# This block is for local development and is ignored by Vercel's production environment
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
