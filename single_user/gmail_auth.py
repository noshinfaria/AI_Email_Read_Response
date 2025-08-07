import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# The scopes your app needs
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail():
    creds = None
    # Check if token.json exists and is not empty
    if os.path.exists('token.json') and os.path.getsize('token.json') > 0:
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception as e:
            print(f"Error loading token.json: {e}")
            os.remove('token.json')  # Corrupted token, remove it

    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Launching OAuth flow... opening browser")
            flow = InstalledAppFlow.from_client_secrets_file(
                'google-credential.json', SCOPES
            )
            creds = flow.run_local_server(port=8000)

        # Save the credentials to token.json
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    # Return Gmail API client
    return build('gmail', 'v1', credentials=creds)
