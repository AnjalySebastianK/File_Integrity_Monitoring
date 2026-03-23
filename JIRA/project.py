import os
import hashlib
import json
from datetime import datetime
import time
import requests
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

MONITORED_FOLDER = "Monitored_Files"
HASH_FILE = "Hash_Database/file_hashes.json"
LOG_FILE = "Logs/fim_changes.json"
ALERT_LOG_FILE = "Logs/fim_alerts.json"

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_URL = os.getenv("JIRA_URL")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Add validation
if not JIRA_EMAIL or not JIRA_API_TOKEN:
    print("[ERROR] JIRA credentials not loaded from .env file!")
    exit(1)

def calculate_sha256(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:#binary
        for block in iter(lambda: f.read(4096), b""):
            sha256.update(block)
    return sha256.hexdigest()


def get_file_metadata(file_path):
    stat = os.stat(file_path)
    return {
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "ctime": stat.st_ctime,
        "permissions": oct(stat.st_mode)[-3:]
    }


def load_old_hashes():
    if not os.path.exists(HASH_FILE):
        return {}
    try:
        with open(HASH_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_hashes(data):
    os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
    with open(HASH_FILE, "w") as f:
        json.dump(data, f, indent=4)


def log_changes(changes):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            logs = json.load(open(LOG_FILE))
        except:
            logs = []
    logs.append(changes)
    json.dump(logs, open(LOG_FILE, "w"), indent=4)


def determine_priority(changes, alerts):
    for alert in alerts:
        if "Deleted" in alert or "Permission Changed" in alert:
            return "High"
    if changes["modified"]:
        return "Medium"
    if changes["added"]:
        return "Low"
    return "Lowest"

def send_email_alert(alerts, priority):
    if not SENDER_EMAIL or not APP_PASSWORD or not RECEIVER_EMAIL:
        print("[EMAIL WARNING] Email credentials not set.")
        return

    subject = f"[FIM ALERT] Priority: {priority}"
    body = "\n\n".join(alerts)

    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()

        print("[EMAIL] Alert sent successfully")

    except Exception as e:
        print("[EMAIL ERROR]", e)

def build_clean_jira_payload(alerts):
    description = " \n \n".join(alerts)

    return {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": "File Integrity Monitoring Alert",
            "description": description,
            "issuetype": {"name": "Incident"}
        },
        "created_at": str(datetime.now())
    }


def save_clean_jira_payload(payload):
    os.makedirs("Logs", exist_ok=True)
    with open("Logs/jira_payload.json", "w") as f:
        json.dump(payload, f, indent=4)
    print("[JIRA] jira_payload.json saved")


def prepare_jira_payload(alerts, changes):
    priority = determine_priority(changes, alerts)

    content = []

    # ADD PRIORITY TO DESCRIPTION
    content.append({
        "type": "paragraph",
        "content": [
            {
                "type": "text",
                "text": f"Priority: {priority}",
                "marks": [{"type": "strong"}]
            }
        ]
    })

    # Separator line
    content.append({
        "type": "paragraph",
        "content": [{"type": "text", "text": "-----------------------------------"}]
    })

    # Existing alerts
    for alert in alerts:
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": alert}]
        })

    return {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": "FIM Alert: File Integrity Violation",
            "priority": {"name": priority},
            "issuetype": {"name": "Incident"},
            "description": {
                "type": "doc",
                "version": 1,
                "content": content
            }
        }
    }



def create_jira_ticket(alerts, changes):
    payload = prepare_jira_payload(alerts, changes)

    credentials = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    token = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    response = requests.post(JIRA_URL, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print("[JIRA] Ticket created:", response.json()["key"])
    else:
        print("[JIRA ERROR]", response.status_code, response.text)


def trigger_alert(changes, old_hashes):
    alerts = []

    for f in changes["added"]:
        alerts.append(f"File Added: {f}")

    for f in changes["modified"]:
        old = old_hashes.get(f, {})
        old_hash = old.get("hash")
        old_meta = old.get("metadata", {})

        path = os.path.join(MONITORED_FOLDER, f)
        new_hash = calculate_sha256(path)
        new_meta = get_file_metadata(path)

        # Hash change

        alerts.append(f"Hash Changed: {f} {old_hash} → {new_hash}")

        if old_meta.get("permissions") != new_meta["permissions"]:
            alerts.append(
                f"Permission Changed: {f} "
                f"{old_meta.get('permissions')} → {new_meta['permissions']}"
            )

        if old_meta.get("size") != new_meta["size"]:
            alerts.append(
                f"Size Changed: {f} "
                f"{old_meta.get('size')} → {new_meta['size']}"
            )

        if old_meta.get("mtime") != new_meta["mtime"]:
            old_time = datetime.fromtimestamp(old_meta.get("mtime")).strftime("%Y-%m-%d %H:%M:%S")
            new_time = datetime.fromtimestamp(new_meta["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            alerts.append(f"Timestamp Changed (mtime): {f} {old_time} → {new_time}")


    for f in changes["deleted"]:
        alerts.append(
            f"File Deleted: {f}\nLast Known Hash: {old_hashes[f]['hash']}"
        )

    if alerts:

        priority = determine_priority(changes, alerts)

        for a in alerts:
            print("[ALERT]", a)

        send_email_alert(alerts, priority)

        clean_payload = build_clean_jira_payload(alerts)
        save_clean_jira_payload(clean_payload)

        create_jira_ticket(alerts, changes)


def check_file_integrity():
    os.makedirs(MONITORED_FOLDER, exist_ok=True)

    old_hashes = load_old_hashes()
    new_hashes = {}

    changes = {
        "timestamp": str(datetime.now()),
        "added": [],
        "modified": [],
        "deleted": []
    }

    current_files = set(os.listdir(MONITORED_FOLDER))
    old_files = set(old_hashes.keys())

    for f in current_files:
        path = os.path.join(MONITORED_FOLDER, f)
        if os.path.isfile(path):
            new_hash = calculate_sha256(path)
            new_meta = get_file_metadata(path)

            new_hashes[f] = {
                "hash": new_hash,
                "metadata": new_meta,
                "last_checked": str(datetime.now())
            }

            if f not in old_hashes:
                changes["added"].append(f)
            else:
                old_hash = old_hashes[f].get("hash")
                old_meta = old_hashes[f].get("metadata")

                if old_hash != new_hash or old_meta != new_meta:
                    changes["modified"].append(f)

    for f in old_files - current_files:
        changes["deleted"].append(f)

    # CORRECT ORDER (ONLY CHANGE)
    log_changes(changes)
    trigger_alert(changes, old_hashes)
    save_hashes(new_hashes)

    print("Integrity Check Completed")
    print(json.dumps(changes, indent=4))


while True:
    check_file_integrity()
    time.sleep(15)
