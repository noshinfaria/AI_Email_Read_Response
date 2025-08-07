import os

# Allow OAuth over HTTP for development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import OAuth2AuthorizationCodeBearer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import os
import json
import base64
from typing import Dict

from sqlalchemy.orm import Session
from multi_user.database import SessionLocal
from multi_user.models import User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()
SCOPES = ['openid', "https://www.googleapis.com/auth/userinfo.email", 'https://www.googleapis.com/auth/gmail.readonly']
CLIENT_SECRETS_FILE = "google-credential.json"
REDIRECT_URI = "http://localhost:8000/oauth2callback"

# In-memory "database" to store tokens per user_id (in production use a real DB!)
user_tokens: Dict[str, dict] = {}

@app.get("/")
def home():
    return {"message": "Welcome! Visit /login to authenticate with Google."}

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@app.get("/login")
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
def oauth2callback(request: Request, db: Session = Depends(get_db)):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials

    # Explicitly fetch user info
    import requests as external_requests
    userinfo_response = external_requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {credentials.token}"}
    )

    if not userinfo_response.ok:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    userinfo = userinfo_response.json()
    user_id = userinfo.get("id")
    email = userinfo.get("email", "")

    # Save or update user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id)

    user.email = email  # Always update email
    user.token = credentials.token
    user.refresh_token = credentials.refresh_token
    user.token_uri = credentials.token_uri
    user.client_id = credentials.client_id
    user.client_secret = credentials.client_secret
    user.scopes = ",".join(credentials.scopes)

    db.add(user)
    db.commit()

    return JSONResponse({"message": f"User {email} logged in and token saved."})




def get_gmail_service(user_id: str, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not authenticated")

    creds = Credentials(
        token=user.token,
        refresh_token=user.refresh_token,
        token_uri=user.token_uri,
        client_id=user.client_id,
        client_secret=user.client_secret,
        scopes=user.scopes.split(",") if user.scopes else []
    )

    # Refresh the token if expired
    from google.auth.transport.requests import Request as GoogleRequest
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())

        # Save updated token
        user.token = creds.token
        db.commit()

    service = build('gmail', 'v1', credentials=creds)
    return service


def process_latest_unread_email_all_users(db: Session):
    users = db.query(User).all()
    if not users:
        print("No users found in the database.")
        return

    for user in users:
        try:
            print(f"Processing for user: {user.email}")
            service = get_gmail_service(user.id, db)
            result = service.users().messages().list(
                userId='me', labelIds=['INBOX'], q="is:unread", maxResults=1
            ).execute()

            messages = result.get("messages", [])
            if not messages:
                print(f"No unread messages for user: {user.email}")
                continue

            msg_id = messages[0]['id']
            msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            payload = msg['payload']
            headers = payload.get('headers', [])

            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No subject')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            snippet = msg.get("snippet", "")

            print(f"[{user.email}] New email from {from_email}: {subject}\nSnippet: {snippet}")

        except Exception as e:
            print(f"Failed to process email for {user.email}: {e}")



@app.post("/gmail/webhook")
async def gmail_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    print("Raw body received:", body)

    if not body:
        return JSONResponse(content={"error": "Empty body"}, status_code=400)
    try:
        envelope = await request.json()
    except Exception as e:
        print("Failed to parse JSON body:", e)
        raise HTTPException(status_code=400, detail="Invalid or missing JSON body")

    if 'message' not in envelope or 'data' not in envelope['message']:
        raise HTTPException(status_code=400, detail="Invalid message format")

    message_data = base64.b64decode(envelope['message']['data']).decode('utf-8')
    print("Received pubsub message:", message_data)

    # Process unread emails for all users
    process_latest_unread_email_all_users(db)

    return JSONResponse(content={"status": "ok"}, status_code=200)



# @app.get("/emails")
# def list_emails(db: Session = Depends(get_db)):
#     users = db.query(User).all()
#     if not users:
#         return {"message": "No users found."}

#     all_emails = []

#     for user in users:
#         try:
#             service = get_gmail_service(user.id, db)
#             results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
#             messages = results.get('messages', [])

#             if not messages:
#                 continue  # Skip users with no messages

#             msg_id = messages[0]['id']
#             msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
#             payload = msg['payload']
#             headers = payload.get('headers', [])

#             subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No subject')
#             from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
#             snippet = msg.get("snippet", "")

#             all_emails.append({
#                 "user_id": user.id,
#                 "email": user.email,
#                 "subject": subject,
#                 "from": from_email,
#                 "snippet": snippet,
#                 "message_id": msg_id,
#             })

#         except Exception as e:
#             all_emails.append({
#                 "user_id": user.id,
#                 "email": user.email,
#                 "error": str(e)
#             })

#     if not all_emails:
#         return {"message": "No messages found for any user."}

#     return {"emails": all_emails}




    
