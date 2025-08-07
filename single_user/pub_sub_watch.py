from single_user.gmail_auth import authenticate_gmail

def setup_watch():
    print("Setting up Gmail watch...")
    service = authenticate_gmail()
    body = {
        "labelIds": ["INBOX"],
        "topicName": "projects/gmail-lead-468305/topics/gmail-notify-topic"
    }
    response = service.users().watch(userId='me', body=body).execute()
    print("Watch response:", response)


if __name__ == "__main__":
    setup_watch()
