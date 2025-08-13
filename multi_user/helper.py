import os
import base64
import json
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest
from multi_user.models import User, users_collection, mail_service_token_collection, state_collection
from multi_user.agent import generate_ai_reply
from multi_user.watch import setup_watch_for_user
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
import requests as external_requests

# Extracted constants (optional, can also keep in main.py)
SCOPES = ['openid',
          "https://www.googleapis.com/auth/userinfo.email",
          'https://www.googleapis.com/auth/gmail.modify']

CLIENT_SECRETS_FILE = "google-credential.json"
REDIRECT_URI = "http://localhost:8000/oauth2_callback"


def create_oauth_flow():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return flow


async def handle_oauth2callback(request: Request) -> HTMLResponse:
    state = request.query_params.get("state")

    # Step 1: Look up user_id from MongoDB
    state_doc = await state_collection.find_one({"state": state})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    
    try:
        user_id = state_doc["user_id"]

        # Step 2: Exchange code for token
        print("Scopes used in Flow:", SCOPES)
        flow = create_oauth_flow()
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials

        # Step 3: Validate required Gmail scopes
        required_scopes = {
            "https://www.googleapis.com/auth/gmail.modify",
        }

        granted_scopes = set(creds.scopes or [])

        missing_scopes = required_scopes - granted_scopes
        if missing_scopes:
            error_message = (
                f"Missing required Gmail scopes: {', '.join(missing_scopes)}. "
                "Please grant these permissions to continue."
            )
            raise HTTPException(status_code=403, detail=error_message)

        userinfo_response = external_requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"}
        )
        if not userinfo_response.ok:
            raise HTTPException(status_code=400, detail="Failed to fetch user info")

        userinfo = userinfo_response.json()
        email = userinfo.get("email", "")

        email = await upsert_user(creds, user_id, email)
        # Step 6: Create Gmail service and setup watch
        service = await get_gmail_service(user_id)
        await setup_watch_for_user(service)
        return JSONResponse({"message": f"User {email} logged in and token saved."})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {e}")


async def upsert_user(credentials, user_id, email):

    user_data = User(
        user_id=user_id,
        email=email,
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        scopes=",".join(credentials.scopes),
        last_history_id=None
    )
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": user_data.dict(by_alias=True, exclude_unset=True)},
        upsert=True
    )
    return user_data.email

async def get_gmail_service(user_id: str):
    user_doc = await users_collection.find_one({"user_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not authenticated")

    user_doc["_id"] = str(user_doc["_id"])
    user = User(**user_doc)

    creds = Credentials(
        token=user.token,
        refresh_token=user.refresh_token,
        token_uri=user.token_uri,
        client_id=user.client_id,
        client_secret=user.client_secret,
        scopes=user.scopes.split(",") if user.scopes else []
    )

    # Refresh the token if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        # Save updated token back to MongoDB
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"token": creds.token}}
        )

    service = build('gmail', 'v1', credentials=creds)
    return service


async def handle_unwatch_gmail(user_id: str):
    try:
        service = await get_gmail_service(user_id)

        # Run blocking Gmail API call in a separate thread
        response = await asyncio.to_thread(
            lambda: service.users().stop(userId="me").execute()
        )
        # Delete user data from database after successful unwatch
        delete_result = await users_collection.delete_one({"user_id": user_id})

        return JSONResponse({
            "message": f"Gmail watch removed for user {user_id}",
            "response": response
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unwatch: {e}")
    

def extract_email_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType')
            if mime_type == 'text/plain':
                data = part['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8')
            if mime_type and mime_type.startswith('multipart/'):
                body = extract_email_body(part)
                if body:
                    return body
    data = payload.get('body', {}).get('data')
    if data:
        return base64.urlsafe_b64decode(data).decode('utf-8')
    return None

async def mark_message_as_read(service, msg_id):
    return service.users().messages().modify(
        userId='me',
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()

async def send_reply(service, msg_id, reply_text, to_email, subject):
    from email.mime.text import MIMEText
    import base64

    message = MIMEText(reply_text)
    message['to'] = to_email
    message['subject'] = "Re: " + subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    send_body = {
        'raw': raw,
        'threadId': msg_id
    }

    return service.users().messages().send(userId='me', body=send_body).execute()

# async def generate_ai_reply(email_body: str) -> str:
#     # Integrate LangChain or AI here
#     return f"Hi, thanks for your email. I have received your message: {email_body[:100]}..."

async def process_message(service, msg_id):
    # Fetch full message
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = payload.get('headers', [])

    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No subject')
    from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
    body = extract_email_body(payload) or "[No body found]"

    print(f"New email from {from_email}: Subject - {subject}\nbody - {body}")

    await asyncio.sleep(2)

    message_status = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Labels']).execute()
    labels = message_status.get('labelIds', [])
    print(f"labels : {labels}")

    if 'UNREAD' in labels:
        print(f"Email {msg_id} still unread, marking as read...")
        await mark_message_as_read(service, msg_id)

        reply_text = await generate_ai_reply(body)

        print(f"Sending AI generated reply to {from_email}...")
        await send_reply(service, msg_id, reply_text, from_email, subject)
    else:
        print(f"Email {msg_id} already read, no action.")


async def handle_gmail_webhook(request_json):
    print("🔍 Handling Gmail webhook data")
    if 'message' not in request_json or 'data' not in request_json['message']:
        print("❌ Invalid message format:", request_json)
        raise HTTPException(status_code=400, detail="Invalid message format")

    print("📦 Decoding base64 message data")
    message_data = base64.b64decode(request_json['message']['data']).decode('utf-8')
    data = json.loads(message_data)
    print("📜 Decoded message payload:", data)

    user_email = data.get("emailAddress")
    history_id = int(data.get("historyId", 0))
    print(f"👤 User Email: {user_email}, History ID: {history_id}")

    print("🔎 Searching for user in database...")
    user_doc = await users_collection.find_one({"email": user_email})
    if not user_doc:
        print("❌ User not found in database:", user_email)
        raise HTTPException(status_code=404, detail="User not found")

    user_doc["_id"] = str(user_doc["_id"])
    user = User(**user_doc)
    print(f"✅ User found: {user.email}, Last History ID: {user.last_history_id}")

    if user.last_history_id is None:
        print("🆕 No last_history_id found, setting it now.")
        await users_collection.update_one(
            {"user_id": user.user_id},
            {"$set": {"last_history_id": history_id}}
        )
        print("✅ Initial historyId set to", history_id)
        return JSONResponse(content={"status": "initial historyId set"}, status_code=200)

    if history_id <= user.last_history_id:
        print(f"ℹ️ No new changes. history_id={history_id}, last_history_id={user.last_history_id}")
        return JSONResponse(content={"status": "no new changes"}, status_code=200)

    print("📬 Getting Gmail service for user")
    service = await get_gmail_service(user.user_id)

    try:
        response = service.users().history().list(
            userId='me',
            startHistoryId=user.last_history_id,
            historyTypes=['messageAdded']
        ).execute()
        print("✅ Gmail history fetched:", response.keys())
    except Exception as e:
        print(f"Error fetching history: {e}, falling back to unread scan.")
        return JSONResponse(content={"error": "History too old or error, please resync."}, status_code=500)

    if 'history' in response:
        print(f"📦 Found {len(response['history'])} history records")
        for record in response['history']:
            if 'messagesAdded' in record:
                print(f"➕ {len(record['messagesAdded'])} new messages added")
                for msg in record['messagesAdded']:
                    msg_id = msg['message']['id']
                    await process_message(service, msg_id)

    new_history_id = max(user.last_history_id, int(response.get('historyId', history_id)))
    await users_collection.update_one(
        {"_id": user.user_id},
        {"$set": {"last_history_id": new_history_id}}
    )

    return JSONResponse(content={"status": "processed changes"}, status_code=200)