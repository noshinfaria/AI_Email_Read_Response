# multi_user/watch.py or similar

from multi_user.database import SessionLocal
from multi_user.models import User
from multi_user.main import get_gmail_service  # Your new multi-user gmail service function

def setup_watch_for_user(service):
    body = {
        "labelIds": ["INBOX"],
        "topicName": "projects/gmail-lead-468305/topics/gmail-notify-topic"
    }
    response = service.users().watch(userId='me', body=body).execute()
    print("Watch response:", response)


def setup_watch_all_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            try:
                service = get_gmail_service(user.id, db)
                setup_watch_for_user(service)
                print(f"Watch set up for user {user.email}")
            except Exception as e:
                print(f"Failed to set up watch for user {user.email}: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    setup_watch_all_users()
