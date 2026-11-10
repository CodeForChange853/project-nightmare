# enable_push.py
from workspace_auth import get_gmail_service

def watch_inbox():
    service = get_gmail_service()
    PROJECT_ID = "project-nightmare-512605"
    topic_name = f"projects/{PROJECT_ID}/topics/gmail-nightmare-topic"
    
    request = {
        # Expanded to include Sent and Draft labels alongside the Inbox
        'labelIds': ['INBOX', 'SENT', 'DRAFT'], 
        'topicName': topic_name
    }
    
    response = service.users().watch(userId='me', body=request).execute()
    print("Push notifications enabled! Gmail is now watching INBOX, SENT, and DRAFT.")
    print(response)

if __name__ == '__main__':
    watch_inbox()