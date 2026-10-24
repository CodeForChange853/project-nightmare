from workspace_auth import get_gmail_service

def watch_inbox():
    service = get_gmail_service()
    
    # Replace with your actual Project ID from Google Cloud Console
    PROJECT_ID = "project-nightmare-512605"
    topic_name = f"projects/{PROJECT_ID}/topics/gmail-nightmare-topic"
    
    request = {
        'labelIds': ['INBOX'],
        'topicName': topic_name
    }
    
    response = service.users().watch(userId='me', body=request).execute()
    print("Push notifications enabled! Gmail is now watching your inbox.")
    print(response)

if __name__ == '__main__':
    watch_inbox()