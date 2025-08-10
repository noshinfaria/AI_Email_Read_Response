## AI Email Read and Reply
This is a project that uses gmail APIs to login for any user and fetch users email dynamically. After two secs if the email stays "UNREAD", this system make it "READ" and reply with an AI generated email.

## Clone Repository
```http
git@github.com:noshinfaria/AI_Email_Read_Response.git
```

## Create and activate virtual environment
```bash
python -m venv venv
venv/Scripts/activate # windows
source venv/bin/activate #linux
```

## install required packages
```bash
pip install -r requirement.txt
```
## Create an app in Google console account
Download json credential and add it in root derectory, rename it as "google-credential.json"

## Run program for multiple user
```bash
uvicorn multi_user.main:app --host 0.0.0.0 --port 8000 --reload
```
## Connect in ngrok
```bash
ngrok http 8000
```
## Add the ngrok domain with API route in Google pub/sub subscription applied link section
Example : https://9f38-xxx.ngrok.io/gmail/webhook
Here API Route: /gmail/webhook

## Execute pub_sub_watch.py file in another terminal tab
```bash
python watch.py
```

Now login with login API
``http
http://localhost/login
```

Send email to that account. You will see real time email fetch in your uvicorn running terminal tab and after two secs it will proceed to find out the email status. If it would be "UNREAD", the system modify it as "READ", generate response of that email body and reply automatically.
