import os
import base64
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from multi_user.models import User, users_collection, state_collection
from multi_user.helper import (
    create_oauth_flow,
    handle_oauth2callback, 
    handle_unwatch_gmail,
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
async def login(user_id: str):
    flow = create_oauth_flow()
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')

    # Save user_id with state in MongoDB
    await state_collection.insert_one({"state": state, "user_id": user_id})

    return RedirectResponse(auth_url)


@app.get("/oauth2_callback")
async def oauth2callback(request: Request):
    return await handle_oauth2callback(request)

@app.post("/gmail/unwatch")
async def unwatch_gmail(user_id: str):
    return await handle_unwatch_gmail(user_id)


@app.post("/gmail/webhook")
async def gmail_webhook(request: Request):
    print("📩 Incoming webhook request")
    try:
        envelope = await request.json()
        print("✅ JSON parsed successfully:", envelope)
    except Exception:
        print("❌ Failed to parse JSON:", e)
        raise HTTPException(status_code=400, detail="Invalid or missing JSON body")

    return await handle_gmail_webhook(envelope)
