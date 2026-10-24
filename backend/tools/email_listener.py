import os
import sqlite3
from google.cloud import pubsub_v1
from workspace_auth import get_gmail_service

# Define your priority and spam rules
PRIORITY_DOMAINS = ['anthropic.com', 'google.com', 'supabase.io', 'vercel.com', 'render.com', 'gloan']
SPAM_DOMAINS = ['temuemail.com']

# Set the path to your new service account key
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(BASE_DIR, "tools", "pubsub-service-account-key.json")
DB_PATH = os.path.join(BASE_DIR, "nightmare.db")

def process_new_email(message_id, service):
    """Fetches the specific email that just arrived and categorizes it."""
    msg = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()
    headers = msg.get('payload', {}).get('headers', [])
    
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender').lower()
    
    # Categorize
    category = "Standard"
    if any(domain in sender for domain in PRIORITY_DOMAINS):
        category = "Priority"
    elif any(domain in sender for domain in SPAM_DOMAINS):
        category = "Temu Spam"
        
    print(f"\n[INSTANT NOTIF] New {category} email from {sender}: {subject}")
    
    # Save to SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
                   (message_id, sender, subject, category, "Pending"))
    conn.commit()
    conn.close()

def start_listening():
    """Starts the Pub/Sub Streaming Pull listener."""
    PROJECT_ID = "project-nightmare-512605" # CHANGE THIS TO YOUR ACTUAL PROJECT ID
    subscription_id = "nightmare-local-sub"
    
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, subscription_id)
    service = get_gmail_service()
    
    last_history_id = None

    def callback(message):
        nonlocal last_history_id
        history_id = message.attributes.get('historyId')
        
        if last_history_id and int(history_id) > int(last_history_id):
            try:
                history = service.users().history().list(userId='me', startHistoryId=last_history_id).execute()
                if 'history' in history:
                    for record in history['history']:
                        if 'messagesAdded' in record:
                            for msg_added in record['messagesAdded']:
                                process_new_email(msg_added['message']['id'], service)
            except Exception as e:
                print(f"Error fetching email details: {e}")
                            
        last_history_id = history_id
        message.ack() 

    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    print(f"Listening for instant email push notifications...\n")
    
    with subscriber:
        try:
            streaming_pull_future.result()
        except TimeoutError:
            streaming_pull_future.cancel()

if __name__ == '__main__':
    start_listening()