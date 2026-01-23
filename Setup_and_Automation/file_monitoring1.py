import os
import hashlib
import json
from datetime import datetime

MONITORED_FOLDER = "Monitored_Files"
HASH_FILE = "Hash_Database/file_hashes.json"

# Calculate SHA-256 hash of a file in chunks.
def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    try:
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                sha256.update(chunk)
    except FileNotFoundError:
        print(f"[ERROR] File not found: {file_path}")
        return None
    except PermissionError:
        print(f"[ERROR] Permission denied: {file_path}")
        return None

    return sha256.hexdigest()

# Create required folders and hash database file if missing.
def ensure_directories():
    os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
    os.makedirs(MONITORED_FOLDER, exist_ok=True)

    if not os.path.exists(HASH_FILE):
        with open(HASH_FILE, "w") as f:
            json.dump({}, f, indent=4)

# Generate SHA-256 hashes for all files in the monitored folder.
def generate_hashes():
    ensure_directories()
    hash_data = {}

    for filename in os.listdir(MONITORED_FOLDER):
        file_path = os.path.join(MONITORED_FOLDER, filename)

        if os.path.isfile(file_path):
            file_hash = calculate_sha256(file_path)

            if file_hash:
                hash_data[filename] = {
                    "hash": file_hash,
                    "last_checked": datetime.now().isoformat()
                }

    with open(HASH_FILE, "w") as json_file:
        json.dump(hash_data, json_file, indent=4)

    print("Hash values generated and stored successfully!")

if __name__ == "__main__":
    generate_hashes()
