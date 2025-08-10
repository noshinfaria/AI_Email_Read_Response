import os
import base64
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from multi_user.models import User, users_collection
from multi_user.helper import (
    create_oauth_flow,
    handle_oauth2callback, 
    handle_gmail_webhook
)
load_dotenv()  # Load environment variables from .env file

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

if not os.getenv("OPENAI_API_KEY"):
    print("Warning: OPENAI_API_KEY environment variable is not set. AI replies will fail.")
    # Optionally exit or continue with degraded functionality
    # sys.exit(1)

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Welcome! Visit /login to authenticate with Google."}

@app.get("/users")
async def get_users():
    users_cursor = users_collection.find({})
    users = []
    async for doc in users_cursor:
        users.append(User(**doc))
    return users

@app.get("/login")
def login():
    flow = create_oauth_flow()
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return RedirectResponse(auth_url)


@app.get("/oauth2_callback")
async def oauth2callback(request: Request):
    return await handle_oauth2callback(str(request.url))


@app.post("/gmail/webhook")
async def gmail_webhook(request: Request):
    try:
        envelope = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or missing JSON body")

    return await handle_gmail_webhook(envelope)
