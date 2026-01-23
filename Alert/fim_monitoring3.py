import os
import hashlib
import json
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

MONITORED_FOLDER = "Monitored_Files"
HASH_FILE = "Hash_Database/file_hashes.json"
LOG_FILE = "Logs/fim_changes.json"
ALERT_LOG_FILE = "Logs/fim_alerts.json"


def send_email_alert(subject, body):
    if not SENDER_EMAIL or not APP_PASSWORD or not RECEIVER_EMAIL:
        print("[EMAIL WARNING] Email credentials not set. Skipping email.")
        return

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

        print("[EMAIL] Alert email sent successfully")

    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {e}")


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    except FileNotFoundError:
        print(f"[ERROR] File not found: {file_path}")
    except PermissionError:
        print(f"[ERROR] Permission denied: {file_path}")
    except Exception as e:
        print(f"[ERROR] Unexpected error hashing {file_path}: {e}")


def load_old_hashes():
    if not os.path.exists(HASH_FILE):
        return {}

    try:
        with open(HASH_FILE, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        print("[WARNING] Hash database corrupted. Recreating...")
        return {}
    except Exception as e:
        print(f"[ERROR] Failed to load hash database: {e}")
        return {}


def save_hashes(hash_data):
    try:
        os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
        with open(HASH_FILE, "w") as file:
            json.dump(hash_data, file, indent=4)
    except Exception as e:
        print(f"[ERROR] Failed to save hash database: {e}")


def log_changes(changes):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r") as file:
                    all_changes = json.load(file)
                    if isinstance(all_changes, dict):
                        all_changes = [all_changes]
            except json.JSONDecodeError:
                print("[WARNING] Log file corrupted. Resetting...")
                all_changes = []
        else:
            all_changes = []

        all_changes.append(changes)

        with open(LOG_FILE, "w") as file:
            json.dump(all_changes, file, indent=4)

    except Exception as e:
        print(f"[ERROR] Failed to write log file: {e}")

# Alert Fun
def trigger_alert(changes, old_hashes, monitored_folder):
    alerts = []

    # Added files
    for file in changes["added"]:
        alerts.append({
            "type": "added",
            "file": file,
            "timestamp": str(datetime.now()),
            "details": f"New file detected: {file}"
        })

    # Modified files
    for file in changes["modified"]:
        old_hash = old_hashes[file]["hash"]
        file_path = os.path.join(monitored_folder, file)
        new_hash = calculate_sha256(file_path)

        alerts.append({
            "type": "modified",
            "file": file,
            "timestamp": str(datetime.now()),
            "old_hash": old_hash,
            "new_hash": new_hash
        })

    # Deleted files
    for file in changes["deleted"]:
        old_hash = old_hashes[file]["hash"]
        alerts.append({
            "type": "deleted",
            "file": file,
            "timestamp": str(datetime.now()),
            "old_hash": old_hash
        })

    # Renamed files
    for rename in changes["renamed"]:
        old_name, new_name = rename.split(" -> ")
        old_hash = old_hashes[old_name]["hash"]
        new_path = os.path.join(monitored_folder, new_name)
        new_hash = calculate_sha256(new_path)

        alerts.append({
            "type": "renamed",
            "old_name": old_name,
            "new_name": new_name,
            "timestamp": str(datetime.now()),
            "old_hash": old_hash,
            "new_hash": new_hash
        })

    if not alerts:
        return

    # Print Alerts
    for alert in alerts:
        print("\n[ALERT]", json.dumps(alert, indent=4))

    # Log Alerts
    try:
        os.makedirs(os.path.dirname(ALERT_LOG_FILE), exist_ok=True)

        if os.path.exists(ALERT_LOG_FILE):
            try:
                with open(ALERT_LOG_FILE, "r") as file:
                    all_alerts = json.load(file)
                    if isinstance(all_alerts, dict):
                        all_alerts = [all_alerts]
            except json.JSONDecodeError:
                all_alerts = []
        else:
            all_alerts = []

        all_alerts.append({
            "timestamp": str(datetime.now()),
            "alerts": alerts
        })

        with open(ALERT_LOG_FILE, "w") as file:
            json.dump(all_alerts, file, indent=4)

    except Exception as e:
        print(f"[ERROR] Failed to write alert log file: {e}")

    # Email alert
    simple_messages = []

    for file in changes["added"]:
        simple_messages.append(f"Please note: A new file was added — {file}")

    for file in changes["modified"]:
        simple_messages.append(f"Please note: A file was modified — {file}")

    for file in changes["deleted"]:
        simple_messages.append(f"Please note: A file was deleted — {file}")

    for rename in changes["renamed"]:
        if " -> " in rename:
            old_name, new_name = rename.split(" -> ")
            simple_messages.append(
                f"Please note: A file was renamed from {old_name} to {new_name}"
            )

    if simple_messages:
        email_subject = "FIM Alert Notification"
        email_body = "\n".join(simple_messages)
        send_email_alert(email_subject, email_body)

    #JIRA payload
    jira_payload = {
        "fields": {
            "project": {"key": "FIM"},
            "summary": f"File Integrity Alert - {len(alerts)} change(s) detected",
            "description": json.dumps(alerts, indent=4),
            "issuetype": {"name": "Incident"}
        }
    }

    print("\n[JIRA PAYLOAD READY]")
    print(json.dumps(jira_payload, indent=4))


def check_file_integrity():
    old_hashes = load_old_hashes()
    new_hashes = {}

    changes = {
        "timestamp": str(datetime.now()),
        "added": [],
        "modified": [],
        "deleted": [],
        "renamed": []
    }

    try:
        current_files = set(os.listdir(MONITORED_FOLDER))
    except Exception as e:
        print(f"[ERROR] Unable to list monitored folder: {e}")
        return

    old_files = set(old_hashes.keys())

    # Reverse lookup: hash → old filename
    old_hash_lookup = {info["hash"]: fname for fname, info in old_hashes.items()}

    # Check added, modified, renamed
    for filename in current_files:
        file_path = os.path.join(MONITORED_FOLDER, filename)

        if os.path.isfile(file_path):
            new_hash = calculate_sha256(file_path)

            if new_hash is None:
                continue

            new_hashes[filename] = {
                "hash": new_hash,
                "last_checked": str(datetime.now())
            }

            if filename not in old_hashes:
                if new_hash in old_hash_lookup:
                    old_name = old_hash_lookup[new_hash]
                    changes["renamed"].append(f"{old_name} -> {filename}")
                else:
                    changes["added"].append(filename)

            elif old_hashes[filename]["hash"] != new_hash:
                changes["modified"].append(filename)

    # Check deleted files
    for filename in old_files - current_files:
        old_hash = old_hashes[filename]["hash"]
        if old_hash not in [info["hash"] for info in new_hashes.values()]:
            changes["deleted"].append(filename)

    save_hashes(new_hashes)
    log_changes(changes)
    trigger_alert(changes, old_hashes, MONITORED_FOLDER)

    print("\nIntegrity Check Completed")
    print(json.dumps(changes, indent=4))


if __name__ == "__main__":
    while True:
        try:
            check_file_integrity()
        except Exception as e:
            print(f"[CRITICAL] Unexpected error in monitoring loop: {e}")

        time.sleep(20)
