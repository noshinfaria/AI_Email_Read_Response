import asyncio
from multi_user.models import users_collection, User  # your Motor collection and User Pydantic model
# from multi_user.helper import get_gmail_service  # keep this function, adjust if needed for async usage

async def setup_watch_for_user(service):
    body = {
        "labelIds": ["INBOX"],
        "topicName": "projects/gmail-lead-468305/topics/gmail-notify-topic"
    }
    response = await asyncio.to_thread(
        lambda: service.users().watch(userId='me', body=body).execute()
    )
    print("Watch response:", response)

# async def setup_watch_user():
#     cursor = users_collection.find({""})
#     async for user_doc in cursor:
#         try:
#             user = User(**user_doc)
#             service = get_gmail_service(user.id)
#             await setup_watch_for_user(service)
#             print(f"Watch set up for user {user.email}")
#         except Exception as e:
#             print(f"Failed to set up watch for user {user_doc.get('email', 'unknown')}: {e}")

# if __name__ == "__main__":
#     asyncio.run(setup_watch_all_users())

