import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define the permissions Nightmare needs (Read-only for Gmail)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Paths to your credentials (resolves automatically based on where this script is located)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

def get_gmail_service():
    """Authenticates using local desktop flow and returns the Gmail service."""
    creds = None
    
    # Check if a valid token already exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
    # If there are no valid credentials, ask the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This spins up a temporary local server and opens your browser for the 1-time login
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_unread_emails(max_results=5):
    """Fetches the latest unread emails from the inbox."""
    try:
        service = get_gmail_service()
        # Query for unread emails in the inbox
        results = service.users().messages().list(userId='me', q='is:unread in:inbox', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print("No unread emails found.")
            return []
            
        email_data = []
        print(f"\n--- Latest {len(messages)} Unread Emails ---")
        for msg in messages:
            msg_detail = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = msg_detail.get('payload', {}).get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            
            email_data.append({'sender': sender, 'subject': subject})
            print(f"From: {sender}\nSubject: {subject}\n")
            
        return email_data
        
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

if __name__ == '__main__':
    print("Testing Google Workspace Authentication...")
    get_unread_emails(max_results=3)