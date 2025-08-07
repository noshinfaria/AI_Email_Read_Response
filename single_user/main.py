from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import base64
from single_user.gmail_auth import authenticate_gmail

app = FastAPI()

@app.post("/gmail/webhook")
async def gmail_webhook(request: Request):
    body = await request.body()
    print("Raw body received:", body)

    if not body:
        return JSONResponse(content={"error": "Empty body"}, status_code=400)
    try:
        envelope = await request.json()
    except Exception as e:
        # Log the error and return 400
        print("Failed to parse JSON body:", e)
        raise HTTPException(status_code=400, detail="Invalid or missing JSON body")

    if 'message' not in envelope or 'data' not in envelope['message']:
        raise HTTPException(status_code=400, detail="Invalid message format")

    message_data = base64.b64decode(envelope['message']['data']).decode('utf-8')
    print("Received pubsub message:", message_data)

    # Process latest unread email
    process_latest_unread_email()

    return JSONResponse(content={"status": "ok"}, status_code=200)

def process_latest_unread_email():
    service = authenticate_gmail()
    result = service.users().messages().list(
        userId='me', labelIds=['INBOX'], q="is:unread", maxResults=1
    ).execute()
    
    messages = result.get("messages", [])
    if not messages:
        return

    msg_id = messages[0]['id']
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = payload.get('headers', [])

    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No subject')
    from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
    snippet = msg.get("snippet", "")

    print(f"New email from {from_email}: {subject}\nSnippet: {snippet}")




