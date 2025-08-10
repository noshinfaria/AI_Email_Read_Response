import os
import base64
import json
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest
from multi_user.models import User, users_collection
from multi_user.agent import generate_ai_reply
from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
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


async def handle_oauth2callback(request_url: str):
    flow = create_oauth_flow()
    flow.fetch_token(authorization_response=request_url)

    credentials = flow.credentials

    userinfo_response = external_requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {credentials.token}"}
    )
    if not userinfo_response.ok:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    userinfo = userinfo_response.json()

    email = await upsert_user(credentials, userinfo)
    return JSONResponse({"message": f"User {email} logged in and token saved."})


async def handle_gmail_webhook(request_json):
    if 'message' not in request_json or 'data' not in request_json['message']:
        raise HTTPException(status_code=400, detail="Invalid message format")

    message_data = base64.b64decode(request_json['message']['data']).decode('utf-8')
    data = json.loads(message_data)

    user_email = data.get("emailAddress")
    history_id = int(data.get("historyId", 0))

    user_doc = await users_collection.find_one({"email": user_email})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    user = User(**user_doc)

    if user.last_history_id is None:
        await users_collection.update_one(
            {"_id": user.id},
            {"$set": {"last_history_id": history_id}}
        )
        return JSONResponse(content={"status": "initial historyId set"}, status_code=200)

    if history_id <= user.last_history_id:
        return JSONResponse(content={"status": "no new changes"}, status_code=200)

    service = await get_gmail_service(user.id)

    try:
        response = service.users().history().list(
            userId='me',
            startHistoryId=user.last_history_id,
            historyTypes=['messageAdded']
        ).execute()
    except Exception as e:
        print(f"Error fetching history: {e}, falling back to unread scan.")
        return JSONResponse(content={"error": "History too old or error, please resync."}, status_code=500)

    if 'history' in response:
        for record in response['history']:
            if 'messagesAdded' in record:
                for msg in record['messagesAdded']:
                    msg_id = msg['message']['id']
                    await process_message(service, msg_id)

    new_history_id = max(user.last_history_id, int(response.get('historyId', history_id)))
    await users_collection.update_one(
        {"_id": user.id},
        {"$set": {"last_history_id": new_history_id}}
    )

    return JSONResponse(content={"status": "processed changes"}, status_code=200)



async def upsert_user(credentials, userinfo):
    user_id = userinfo.get("id")
    email = userinfo.get("email", "")

    user_data = User(
        _id=user_id,
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
        {"_id": user_data.id},
        {"$set": user_data.dict(by_alias=True, exclude_unset=True)},
        upsert=True
    )
    return email

async def get_gmail_service(user_id: str):
    user_doc = await users_collection.find_one({"_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not authenticated")

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
            {"_id": user.id},
            {"$set": {"token": creds.token}}
        )

    service = build('gmail', 'v1', credentials=creds)
    return service

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

    if 'UNREAD' in labels:
        print(f"Email {msg_id} still unread, marking as read...")
        await mark_message_as_read(service, msg_id)

        reply_text = await generate_ai_reply(body)

        print(f"Sending AI generated reply to {from_email}...")
        await send_reply(service, msg_id, reply_text, from_email, subject)
    else:
        print(f"Email {msg_id} already read, no action.")
