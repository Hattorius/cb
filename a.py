import os
import re
import requests
import json
import random
import time
import threading
import pickle
import gc
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

# Global settings
MAX_WORKERS = 500
TIMEOUT = 1
MIN_USERNAME_LENGTH = 6
output_lock = threading.Lock()
processed_count = 0
valid_count = 0

# Session pool
SESSION_POOL = Queue()
for _ in range(MAX_WORKERS):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        "Accept": "application/json",
        "Origin": "https://www.coinbase.com"
    })
    SESSION_POOL.put(session)

# Allowed email domains
ALLOWED_EMAIL_DOMAINS = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
                        'aol.com', 'comcast.net', 'sbcglobal.net', 'live.com', 'msn.com'}

# Load filters
DICTIONARY_WORDS = set()
NAMES_DATASET = set()

try:
    with open("words_dictionary.json", "r") as f:
        DICTIONARY_WORDS = set(json.load(f).keys())
except:
    pass

try:
    with open("names_dataset.txt", "r") as f:
        NAMES_DATASET = {line.strip().lower() for line in f if line.strip()}
except:
    pass

# Load proxies
PROXIES = []
try:
    with open("proxies.txt", "r") as f:
        for line in f:
            if '@' in line:
                parts = line.strip().split('@')
                if len(parts) == 2:
                    auth, ip_port = parts
                    user, password = auth.split(':')
                    PROXIES.append({"http": f"http://{user}:{password}@{ip_port}", 
                                  "https": f"http://{user}:{password}@{ip_port}"})
except:
    print("Warning: proxies.txt not found")

def should_skip(username, email):
    if not username or not email or '@' not in email:
        return True
    if len(username) < MIN_USERNAME_LENGTH:
        return True
    domain = email.lower().split('@')[-1]
    if domain not in ALLOWED_EMAIL_DOMAINS:
        return True
    username_lower = username.lower()
    if username_lower in DICTIONARY_WORDS and re.match(r'^[a-z]+$', username_lower):
        return True
    if username_lower in NAMES_DATASET and re.match(r'^[a-z]+$', username_lower):
        return True
    return False

def check_coinbase(username, email):
    global processed_count, valid_count
    
    if should_skip(username, email):
        return
    
    url = f"https://api.wallet.coinbase.com/rpc/v2/destination/resolve?query={username}.cb.id&assetCode=eth"
    
    session = SESSION_POOL.get()
    proxy = random.choice(PROXIES) if PROXIES else None
    
    try:
        response = session.get(url, proxies=proxy, timeout=TIMEOUT)
        response_text = response.text
        
        # Show API response for debugging
        print(f"{username}: {response_text}")
        
        if response.status_code == 200:
            try:
                data = json.loads(response_text)
                
                if "result" in data and data["result"] and "data" in data["result"] and "address" in data["result"]["data"]:
                    address = data["result"]["data"]["address"]
                    cb_id = f"{username}.cb.id"
                    
                    with output_lock:
                        with open("output.txt", "a") as f:
                            f.write(f"{email},{cb_id},{address}\n")
                        valid_count += 1
                        print(f"VALID: {username}")
                else:
                    print(f"INVALID: {username}")
            except:
                pass
    except:
        pass
    finally:
        SESSION_POOL.put(session)
        processed_count += 1

def main():
    global processed_count, valid_count
    processed_count = 0
    valid_count = 0
    
    print(f"Starting with {MAX_WORKERS} workers, {len(PROXIES)} proxies")
    
    # Create output file
    with open("output.txt", "w") as f:
        f.write("email,cb.id,address\n")
    
    # Find pickle files
    pkl_files = [f for f in os.listdir('.') if f.endswith('.pkl')]
    
    if not pkl_files:
        print("No pickle files found")
        return
    
    random.shuffle(pkl_files)
    start_time = time.time()
    
    for pkl_file in pkl_files:
        print(f"Processing {pkl_file}...")
        
        try:
            with open(pkl_file, 'rb') as f:
                data = pickle.load(f)
        except:
            continue
        
        # Random starting position
        start_index = random.randint(0, max(0, len(data) - 10000))
        print(f"Starting from position {start_index}")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for i in range(start_index, len(data)):
                entry = data[i]
                username = entry.get('username')
                email = entry.get('email')
                
                if username and email:
                    futures.append(executor.submit(check_coinbase, username, email))
                
                # Update progress
                if len(futures) % 1000 == 0:
                    elapsed = time.time() - start_time
                    speed = processed_count / elapsed if elapsed > 0 else 0
                    cpm = speed * 60
                    print(f"\rProcessed: {processed_count} | Valid: {valid_count} | Speed: {speed:.1f}/sec ({cpm:.0f} CPM)", end="")
            
            # Wait for all to complete
            for future in futures:
                future.result()
    
    elapsed = time.time() - start_time
    speed = processed_count / elapsed if elapsed > 0 else 0
    print(f"\n\nCompleted! Processed {processed_count} in {elapsed:.1f} seconds")
    print(f"Average speed: {speed:.1f}/sec ({speed * 60:.0f} CPM)")
    print(f"Found {valid_count} valid accounts")

if __name__ == "__main__":
    main()