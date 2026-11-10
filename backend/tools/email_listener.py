import asyncio
import json
import os
import re
import sqlite3
from typing import Set
from google.cloud import pubsub_v1

try:
    from .workspace_auth import get_gmail_service
except (ImportError, ValueError):
    try:
        from tools.workspace_auth import get_gmail_service
    except (ImportError, ValueError):
        from workspace_auth import get_gmail_service

# Define your priority, spam, and personal sender rules
PRIORITY_DOMAINS = ['anthropic.com', 'google.com', 'supabase.io', 'vercel.com', 'render.com', 'gloan']
SPAM_DOMAINS = ['temuemail.com', 'temu.com']
PERSONAL_DOMAINS = [
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
    'icloud.com', 'proton.me', 'protonmail.com', 'live.com', 'me.com'
]
AUTOMATED_KEYWORDS = [
    'noreply', 'no-reply', 'notification', 'notifications', 'newsletter', 'mailer-daemon',
    'marketing', 'updates', 'digest', 'promo', 'automated', 'support@', 'billing@', 'alert@',
    'alerts@', 'news@', 'donotreply', 'invitations@', 'bounce'
]

# Set the path to your new service account key
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(BASE_DIR, "tools", "pubsub-service-account-key.json")
DB_PATH = os.path.join(BASE_DIR, "nightmare.db")


def is_person_email(headers: list, sender_raw: str) -> bool:
    """
    Determines if an email was sent by an individual person rather than an automated robot,
    marketing blast, or generic mailing list. Personal correspondence is treated as Priority.
    """
    sender = sender_raw.strip()
    sender_lower = sender.lower()

    # 1. Automated / bulk checks from standard RFC headers
    for h in headers:
        name = (h.get('name') or '').lower()
        val = (h.get('value') or '').lower()
        if name in ('precedence', 'x-precedence') and any(b in val for b in ('bulk', 'junk', 'list')):
            return False
        if name in ('list-unsubscribe', 'list-id', 'list-help', 'list-archive'):
            return False

    # 2. Check for bot / automated keywords in sender address
    if any(kw in sender_lower for kw in AUTOMATED_KEYWORDS):
        return False

    # 3. Check for human display name (e.g. "Garcia Sabar <garciasabar12@gmail.com>")
    if '<' in sender:
        display_name = sender.split('<')[0].strip(' "“\'')
        words = [w for w in re.split(r'[\s,._-]+', display_name) if w.isalpha()]
        if len(words) >= 1 and not any(kw in display_name.lower() for kw in AUTOMATED_KEYWORDS):
            return True

    # 4. If from a common personal email domain (gmail, yahoo, etc.) and not automated
    if any(dom in sender_lower for dom in PERSONAL_DOMAINS):
        return True

    return False


class EmailEventDispatcher:
    """Thread-safe event dispatcher for broadcasting real-time email events to active SSE connections."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def dispatch(self, event: dict) -> None:
        """Dispatches an event payload thread-safely to all subscribers and global queue."""
        def _broadcast():
            # Put into global queue
            try:
                if email_event_queue.full():
                    try:
                        email_event_queue.get_nowait()
                    except Exception:
                        pass
                email_event_queue.put_nowait(event)
            except Exception:
                pass

            # Broadcast to active subscriber queues
            sub_count = len(self._subscribers)
            print(f"[SSE DISPATCH] Broadcasting '{event.get('type')}' event ({event.get('subject')}) to {sub_count} active subscriber(s)")
            for q in list(self._subscribers):
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except Exception:
                            pass
                    q.put_nowait(event)
                except Exception:
                    pass

        loop = self._loop
        if loop is None or not loop.is_running():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        if loop and loop.is_running():
            try:
                current_loop = None
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

                if current_loop is loop:
                    _broadcast()
                else:
                    loop.call_soon_threadsafe(_broadcast)
            except Exception as ex:
                print(f"[SSE DISPATCH] Warning: threadsafe call failed ({ex}), calling directly")
                _broadcast()
        else:
            _broadcast()


# Global asyncio.Queue and EventDispatcher instances
email_event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
email_event_dispatcher = EmailEventDispatcher()


def get_email_db_connection():
    # Required to prevent "SQLite objects created in a thread can only be used in that same thread" errors
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS email_state (id TEXT, sender TEXT, subject TEXT, category TEXT, status TEXT)"
    )
    return conn


# email_listener.py (Update process_new_email)
def process_new_email(message_id, service):
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()
    except Exception as e:
        print(f"Failed to fetch email {message_id}: {e}")
        return

    headers = msg.get('payload', {}).get('headers', [])
    labels = msg.get('labelIds', [])
    
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    sender_raw = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
    sender = sender_raw.lower()
    subject_lower = subject.lower()

    conn = get_email_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM email_state WHERE id = ?", (message_id,))
    if cursor.fetchone():
        conn.close()
        return

    # Advanced categorization logic
    category = "Standard"
    
    if 'DRAFT' in labels:
        category = "Drafts"
    elif 'SENT' in labels:
        category = "Sent"
    elif any(domain in sender for domain in SPAM_DOMAINS):
        category = "Temu Spam"
    elif any(kw in subject_lower or kw in sender for kw in ['receipt', 'invoice', 'order', 'shopee', 'lazada', 'payment']):
        category = "Purchases"
    elif any(kw in subject_lower or kw in sender for kw in ['flight', 'itinerary', 'agoda', 'cebu pacific', 'hotel']):
        category = "Travel"
    elif any(domain in sender for domain in PRIORITY_DOMAINS) or is_person_email(headers, sender_raw):
        category = "Priority"
        
    print(f"\n[INSTANT NOTIF] New {category} email from {sender_raw}: {subject}")
    
    cursor.execute(
        "INSERT INTO email_state (id, sender, subject, category, status) VALUES (?, ?, ?, ?, ?)",
        (message_id, sender_raw, subject, category, "Pending")
    )
    conn.commit()
    conn.close()

    # Trigger real-time SSE event
    event_payload = {
        "type": "new_email",
        "id": str(message_id),
        "category": category,
        "sender": sender_raw,
        "subject": subject,
        "status": "Pending",
    }
    email_event_dispatcher.dispatch(event_payload)


_service = None
_last_history_id = None


def get_service():
    global _service, _last_history_id
    if _service is None:
        _service = get_gmail_service()
        if _last_history_id is None:
            try:
                profile = _service.users().getProfile(userId='me').execute()
                _last_history_id = profile.get('historyId')
            except Exception as e:
                print(f"Could not initialize starting historyId: {e}")
    return _service


def process_email_message(message):
    """Message callback fired by Google's background gRPC thread."""
    global _last_history_id
    service = get_service()

    # Extract historyId from message data (JSON payload) or message attributes
    history_id = None
    try:
        if message.data:
            data = json.loads(message.data.decode('utf-8'))
            history_id = data.get('historyId')
    except Exception:
        pass
    if not history_id:
        history_id = message.attributes.get('historyId')

    processed = False
    if _last_history_id and history_id and int(history_id) > int(_last_history_id):
        try:
            history = service.users().history().list(
                userId='me', startHistoryId=_last_history_id, historyTypes=['messageAdded']
            ).execute()
            if 'history' in history:
                for record in history['history']:
                    if 'messagesAdded' in record:
                        for msg_added in record['messagesAdded']:
                            process_new_email(msg_added['message']['id'], service)
                            processed = True
        except Exception as e:
            print(f"Error fetching email details: {e}")

    # Fallback: if first pull or history delta missed, scan recent unrecorded messages
    if not processed:
        try:
            latest = service.users().messages().list(userId='me', maxResults=3).execute()
            for m in latest.get('messages', []):
                process_new_email(m['id'], service)
        except Exception as e:
            print(f"Error during fallback email check: {e}")

    if history_id:
        _last_history_id = history_id
    message.ack()


def start_listening():
    """Starts the Pub/Sub Streaming Pull listener."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-nightmare-512605")
    subscription_id = "nightmare-local-sub"
    
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=process_email_message)
    print(f"Listening for instant email push notifications on {subscription_path}...\n")
    
    with subscriber:
        try:
            streaming_pull_future.result()
        except TimeoutError:
            streaming_pull_future.cancel()


if __name__ == '__main__':
    start_listening()
