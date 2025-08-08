## Gmail_and_Lead_Collection
This is a project that uses gmail APIs to login for any user and fetch users email dynamically to collect leads.

## Clone Repository
```http
git@github.com:noshinfaria/Gmail_and_Lead_Collection.git
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
python pub_sub_watch.py
```

Now login with login API and send email to that account. You will see real time email ofetch in your uvicorn running terminal tab.
