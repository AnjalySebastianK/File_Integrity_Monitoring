import os
import hashlib
import json
from datetime import datetime
import time

MONITORED_FOLDER = "Monitored_Files"
HASH_FILE = "Hash_Database/file_hashes.json"
LOG_FILE = "Logs/fim_changes.json"


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

    return None


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

def check_file_integrity():
    if not os.path.exists(MONITORED_FOLDER):
        print(f"[ERROR] Monitored folder not found: {MONITORED_FOLDER}")
        os.makedirs(MONITORED_FOLDER, exist_ok=True)
        print("[INFO] Created missing monitored folder.")
        return

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
                continue  # Skip unreadable files

            new_hashes[filename] = {
                "hash": new_hash,
                "last_checked": str(datetime.now())
            }

            if filename not in old_hashes:
                # Check if hash matches an old file → rename
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

    print("\nIntegrity Check Completed")
    print(json.dumps(changes, indent=4))


while True:
    try:
        check_file_integrity()
    except Exception as e:
        print(f"[CRITICAL] Unexpected error in monitoring loop: {e}")

    time.sleep(20)
 
