# Import suppression utilities first - MUST be before any other imports
import suppress_tf_logs
old_stdout, old_stderr = suppress_tf_logs.suppress_stdout()

# Ensure TensorFlow is imported silently
suppress_tf_logs.silence_tensorflow()

# Standard imports
import src, time, json, os, random, logging, traceback
import requests
import re # <-- ADD THIS IMPORT
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
import threading
from tqdm import tqdm
from colorama import Fore, Style, init # Import colorama
import platform # For clear_screen
import questionary # For interactive menu
from unidecode import unidecode
import hashlib # <-- ADD HASHING LIBRARY

# Import TensorFlow again to ensure it's available in this context
import tensorflow

# Restore stdout and stderr
suppress_tf_logs.restore_stdout(old_stdout, old_stderr)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Xool - Roblox Clothing Automation Tool")
parser.add_argument('--debug', action='store_true', help='Enable debug output')
parser.add_argument('--config', type=str, default='config.json', help='Path to config file')
args = parser.parse_args()

# Configure logging based on debug flag
if args.debug:
    log_level = logging.DEBUG
    tensorflow.get_logger().setLevel(logging.WARNING)
else:
    log_level = logging.INFO
    tensorflow.get_logger().setLevel(logging.FATAL)
    
# Define colors for different log levels
LOG_COLORS = {
    logging.DEBUG: Fore.CYAN,
    logging.INFO: Fore.GREEN,
    logging.WARNING: Fore.YELLOW,
    logging.ERROR: Fore.RED,
    logging.CRITICAL: Fore.RED + Style.BRIGHT,
}

class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None, style='%', use_color=True):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.use_color = use_color

    def format(self, record):
        # Get the original formatted message
        log_msg = super().format(record)
        # Add color based on level
        if self.use_color and record.levelno in LOG_COLORS:
            log_msg = LOG_COLORS[record.levelno] + log_msg + Style.RESET_ALL
        return log_msg

class Statistics:
    def __init__(self):
        self.start_time = datetime.now()
        self.lock = threading.Lock()  # Initialize lock first
        self.reset()  # Now call reset
        
    def reset(self):
        with self.lock:
            self.total_processed = 0
            self.successful_uploads = 0
            self.failed_uploads = 0
            self.duplicates_found = 0
            self.nsfw_detected = 0
            self.errors = []
            self.last_successful_upload = None
            
    def add_success(self):
        with self.lock:
            self.successful_uploads += 1
            self.total_processed += 1
            self.last_successful_upload = datetime.now()
            
    def add_failure(self, reason: str):
        with self.lock:
            self.failed_uploads += 1
            self.total_processed += 1
            self.errors.append((datetime.now(), reason))
            
    def add_duplicate(self):
        with self.lock:
            self.duplicates_found += 1
            self.total_processed += 1
            
    def add_nsfw(self):
        with self.lock:
            self.nsfw_detected += 1
            self.total_processed += 1
            
    def get_summary(self) -> Dict[str, Any]:
        with self.lock:
            runtime = datetime.now() - self.start_time
            success_rate = (self.successful_uploads / self.total_processed * 100 
                          if self.total_processed > 0 else 0)
            return {
                "runtime": str(runtime),
                "total_processed": self.total_processed,
                "successful_uploads": self.successful_uploads,
                "failed_uploads": self.failed_uploads,
                "duplicates_found": self.duplicates_found,
                "nsfw_detected": self.nsfw_detected,
                "success_rate": f"{success_rate:.1f}%",
                "last_successful": (
                    str(self.last_successful_upload) 
                    if self.last_successful_upload else "None"
                ),
                "recent_errors": self.errors[-5:] if self.errors else []
            }

# --- Helper Function to Load Lists --- 
def load_list_from_file(filepath: str) -> list:
    """Loads a list of strings from a file, one item per line."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Read lines, strip whitespace, filter out empty lines and comments
            items = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        if not items:
             logging.warning(f"File '{filepath}' is empty or contains only comments.")
        return items
    except FileNotFoundError:
        logging.error(f"File not found: '{filepath}'. Using empty list.")
        return []
    except Exception as e:
        logging.error(f"Error reading file '{filepath}': {e}. Using empty list.")
        return []
# --- End Helper Function ---

# --- Define Log File Path ---
UPLOAD_LOG_FILE = os.path.join(os.getcwd(), "src", "assets", "upload_logs", "upload_log.txt")

# --- Helper Function: Calculate File Hash ---
def calculate_file_hash(file_path: str) -> Optional[str]:
    """Calculates the SHA256 hash of a file."""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as file:
            while True:
                chunk = file.read(4096) # Read in chunks for large files
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        logging.error(f"[Hash] File not found: {file_path}")
        return None
    except Exception as e:
        logging.error(f"[Hash] Error hashing file {file_path}: {e}")
        return None

# --- Helper Function: Load Upload Log ---
def load_upload_log(log_file_path: str) -> set:
    """Loads previously uploaded group_id,hash pairs from the log file."""
    uploaded_set = set()
    if not os.path.exists(log_file_path):
        logging.info(f"Upload log file not found at '{log_file_path}'. Assuming no previous uploads.")
        return uploaded_set
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith('#'): # Skip empty lines and comments
                    continue
                parts = line.split(',')
                if len(parts) == 2:
                    group_id = parts[0].strip()
                    image_hash = parts[1].strip()
                    if group_id and image_hash:
                        uploaded_set.add((group_id, image_hash))
                    else:
                        logging.warning(f"[Log Load] Skipping malformed line {line_num+1} in '{log_file_path}': Invalid format.")
                else:
                    logging.warning(f"[Log Load] Skipping malformed line {line_num+1} in '{log_file_path}': Expected 2 parts separated by comma.")
        logging.info(f"Loaded {len(uploaded_set)} previously uploaded records from '{log_file_path}'.")
    except Exception as e:
        logging.error(f"[Log Load] Error reading log file '{log_file_path}': {e}. Proceeding with empty log.")
        return set() # Return empty set on error
    return uploaded_set

# --- Helper Function: Append to Upload Log ---
def append_to_upload_log(log_file_path: str, group_id: str, image_hash: str):
    """Appends a new successful upload record to the log file."""
    try:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file_path)
        os.makedirs(log_dir, exist_ok=True)
        
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"{group_id},{image_hash}\n")
        logging.debug(f"[Log Append] Appended record: Group {group_id}, Hash {image_hash[:8]}...")
    except Exception as e:
        logging.error(f"[Log Append] Failed to append to log file '{log_file_path}': {e}")

class xool:
    current_directory = os.getcwd()
    types = ["classicshirts", "classicpants"]
    def __init__(self, config: Dict, search_keywords: List[str], blacklisted_words: List[str]):
        self.stats = Statistics()
        self.config = config # Store the rest of the config dict
        self.search_keywords = search_keywords # Store loaded keywords
        self.blacklisted_words = blacklisted_words # Store loaded blacklist
        if config.get("delete_all_images_on_restart", False):
            logging.info("Clearing existing non-template assets based on config.")
            src.files.remove_png()
            
        # Set default duplicate detection parameters if not present
        if "duplicate_detection" not in self.config:
            self.config["duplicate_detection"] = {
                "use_advanced": True,
                "min_algorithm_matches": 2,
                "thresholds": {
                    "phash": 3,
                    "dhash": 3,
                    "ahash": 5,
                    "whash": 3,
                    "colorhash": 4
                }
            }
        
        # Set default search strategy if not present
        if "search_strategy" not in self.config:
            self.config["search_strategy"] = {
                "mode": "random",  # Options: "popular", "newest", "relevant", "random"
                "min_price": 5,
                "max_price": 0,    # 0 means no limit
                "limit": 120       # Max items to fetch per search
            }
            
        # --- Upload logic ---
        # Ensure groups key exists and is a dictionary
        if not isinstance(self.config.get("groups"), dict):
             logging.error("'groups' key missing or invalid in config.json. Cannot start upload process.")
             return # Stop initialization if groups config is bad

        for group_id_str, group_config in self.config["groups"].items():
             if not isinstance(group_config, dict) or "uploader_cookies" not in group_config or not isinstance(group_config["uploader_cookies"], list):
                 logging.warning(f"Invalid configuration for group {group_id_str}. Skipping.")
                 continue
             
             group_id = group_id_str # Keep group_id as string from dict key
             logging.info(f"Starting upload process for Group ID: {group_id}")
             
             cookies_for_group = group_config["uploader_cookies"]
             if not cookies_for_group:
                 logging.warning(f"No cookies provided for group {group_id}. Skipping upload for this group.")
                 continue

             # Use the first cookie for this group (or implement multi-cookie logic if needed)
             # For simplicity, using the first valid cookie.
             # You might want round-robin or random selection if multiple cookies are meant for load balancing.
             cookie_str = cookies_for_group[0] 
             if not cookie_str:
                 logging.warning(f"Empty cookie string found for group {group_id}. Skipping.")
                 continue
                 
             try:
                # Pass group_id as string
                self.upload(cookie_str, group_id) 
             except Exception as e:
                 logging.error(f"Unhandled exception during upload process for group {group_id}: {e}")
                 if args.debug:
                    logging.error(traceback.format_exc())
                
        # Print final statistics
        self.print_statistics()

    def print_statistics(self):
        """Print current statistics in a formatted way"""
        stats = self.stats.get_summary()
        logging.info("\n=== Upload Statistics ===")
        logging.info(f"Runtime: {stats['runtime']}")
        logging.info(f"Total Processed: {stats['total_processed']}")
        logging.info(f"Successful Uploads: {stats['successful_uploads']}")
        logging.info(f"Failed Uploads: {stats['failed_uploads']}")
        logging.info(f"Duplicates Found: {stats['duplicates_found']}")
        logging.info(f"NSFW Detected: {stats['nsfw_detected']}")
        logging.info(f"Success Rate: {stats['success_rate']}")
        logging.info(f"Last Successful Upload: {stats['last_successful']}")
        if stats['recent_errors']:
            logging.info("\nRecent Errors:")
            for timestamp, error in stats['recent_errors']:
                logging.info(f"  {timestamp}: {error}")
        logging.info("=====================")

    def upload(self, cookie, group_id):
        # --- Load Upload Log at the start of the upload session for this group ---
        uploaded_set = load_upload_log(UPLOAD_LOG_FILE)
        # ---------------------------------------------------------------------
        
        if not cookie:
            raise Exception("Empty cookie")
        cookie = src.cookie.cookie(cookie)
        dn_stop = True
        while dn_stop:
            try:
                current_type = random.choice(self.types)
                
                # Get search strategy parameters safely
                strategy_config = self.config.get("search_strategy", {})
                strategy = strategy_config.get("mode", "random") # Default to random if missing
                search_params = src.scrape.get_optimal_sort_params(strategy)
                
                # Add additional search parameters safely
                search_params.update({
                    "limit": strategy_config.get("limit", 120),
                    "minPrice": strategy_config.get("min_price", 5)
                })
                max_price = strategy_config.get("max_price", 0)
                if max_price > 0:
                    search_params["maxPrice"] = max_price

                keywords_list = self.search_keywords
                if not keywords_list:
                    logging.warning("No search keywords loaded from search_keywords.txt. Skipping search cycle.")
                    time.sleep(5)
                    continue

                # Select one keyword RANDOMLY from the list
                search_keyword = random.choice(keywords_list)

                # Log search info (removed index)
                logging.info(f"Searching for {current_type} using keyword: '{search_keyword}'")

                # Use the selected keyword for scraping
                items = src.scrape.scrape_assets(
                    cookie,
                    search_keyword, # Use the randomly selected keyword
                    current_type,
                    search_params,
                    debug_mode=args.debug
                )
                logging.info(f"Found {len(items)} potential items for keyword '{search_keyword}'")
                
                random.shuffle(items)
                scraped = src.scrape.sort_assets(
                    cookie, 
                    items[:5], 
                    self.config.get("blacklisted_creators", []), # Use .get for safety
                    self.blacklisted_words, # Use loaded blacklist from instance variable
                    self.config.get("upload_without_blacklisted_words", False) # Use .get for safety
                )
                
                # Process items with progress bar
                with tqdm(scraped, desc="Processing items", unit="item") as pbar:
                    for item in pbar:
                        pbar.set_description(f"Processing {item['name'][:30]}...")
                        
                        # --- Get path from download --- 
                        path = src.download.save_asset(
                            cookie, 
                            item["id"], 
                            "shirts" if current_type == "classicshirts" else "pants", 
                            item["name"], 
                            self.config["max_nudity_value"], 
                            self.current_directory, 
                            self.config, # <-- Pass the config dictionary
                            debug_mode=args.debug
                        )
                        if not path:
                            logging.info(f"No path found skipping: {item['name']}")
                            self.stats.add_failure("Download failed")
                            continue

                        # --- CHECK UPLOAD LOG --- 
                        image_hash = calculate_file_hash(path)
                        if not image_hash: # Handle hashing error
                            self.stats.add_failure("Hashing failed")
                            continue 
                        
                        if (group_id, image_hash) in uploaded_set:
                            logging.info(f"Skipping item {item['name']} (Hash: {image_hash[:8]}...): Already uploaded to group {group_id}.")
                            self.stats.add_failure("Already Uploaded") # Count as failure for this run's stats
                            continue
                        # --- END CHECK UPLOAD LOG ---
                        
                        if self.config["require_one_tag_in_name"]:
                            if not any(value.lower() in os.path.basename(path).lower().split(" ") 
                                     for value in self.config["searching_tags"].split(",")):
                                logging.info(f"No required tag found skipping: {item['name']}")
                                self.stats.add_failure("Missing required tag")
                                continue
                        
                        # Advanced duplicate check after download
                        if self.config["dupe_check"]:
                            dup_config = self.config.get("duplicate_detection", {})
                            use_advanced = dup_config.get("use_advanced", True)
                            
                            if use_advanced:
                                # Use the advanced similarity check with custom thresholds
                                thresholds = dup_config.get("thresholds", {
                                    "phash": 3,
                                    "dhash": 3,
                                    "ahash": 5,
                                    "whash": 3, 
                                    "colorhash": 4
                                })
                                min_matches = dup_config.get("min_algorithm_matches", 2)
                                
                                is_duplicate, reason = src.files.detect_duplicate(
                                    path, 
                                    current_type,
                                    use_advanced=True,
                                    debug_mode=args.debug
                                )
                                
                                if is_duplicate:
                                    logging.info(f"Found similar clothing skipping: {item['name']} - Reason: {reason}")
                                    self.stats.add_duplicate()
                                    continue
                            else:
                                # Fall back to the original similarity check
                                if src.files.is_similar(path, current_type, debug_mode=args.debug):
                                    logging.info(f"Found similar clothing skipping: {item['name']}")
                                    self.stats.add_duplicate()
                                    continue
                        
                        item_uploaded = src.upload.create_asset(
                            item["name"], 
                            path, 
                            "shirt" if current_type == "classicshirts" else "pants", 
                            cookie, 
                            group_id, 
                            self.config["description"], 
                            5, 
                            5
                        )
                        if item_uploaded is False:
                            self.stats.add_failure("Upload failed")
                            return
                        elif item_uploaded == 2:
                            logging.info(f"Failed to upload skipping (not enough funds): {item['name']}")
                            self.stats.add_failure("Insufficient funds")
                            continue
                        elif item_uploaded == 3:
                            logging.info(f"Failed to upload skipping (no permission): {item['name']}")
                            self.stats.add_failure("No permission")
                            continue
                            
                        # item_uploaded now directly contains the asset ID on success
                        # No need to extract it: OLD: item_uploaded['response']['assetId']
                        response = src.upload.release_asset(
                            cookie, 
                            item_uploaded['response']['assetId'], # Reverted: Access dict
                            self.config["assets_price"], 
                            item["name"], 
                            self.config["description"], 
                            group_id
                        )
                        # Check the response object returned by release_asset
                        if response and response.status_code == 200:
                             try:
                                 response_json = response.json()
                                 if response_json.get("status") == 0:
                                     # Log the extracted asset ID
                                     logging.info(f"Released item. ID {item_uploaded['response']['assetId']}")
                                     self.stats.add_success()
                                     if self.config["upload_amount"] > 1:
                                         self.config["upload_amount"] -= 1
                                     elif self.config["upload_amount"] == 1:
                                         dn_stop = False # Assuming this logic is still correct
                                     
                                     # --- APPEND TO UPLOAD LOG ON SUCCESS --- 
                                     append_to_upload_log(UPLOAD_LOG_FILE, group_id, image_hash)
                                     uploaded_set.add((group_id, image_hash)) # Update in-memory set
                                     # ---------------------------------------
                                 else:
                                     # Handle non-zero status in JSON
                                     logging.error(f"Failed to release item {item['name']} (ID: {item_uploaded['response']['assetId']}). Status: {response.status_code}, Response: {response.text}")
                                     self.stats.add_failure("Release failed (API Error)")
                             except json.JSONDecodeError:
                                 logging.error(f"Failed to decode release response for item {item['name']} (ID: {item_uploaded['response']['assetId']}). Status: {response.status_code}, Response: {response.text}")
                                 self.stats.add_failure("Release failed (Decode Error)")
                        elif response:
                            # Handle non-200 status code from release_asset
                            logging.error(f"Failed to release item {item['name']} (ID: {item_uploaded['response']['assetId']}). Status: {response.status_code}, Response: {response.text}")
                            self.stats.add_failure("Release failed (HTTP Error)")
                        else:
                            # Handle case where release_asset returned None
                            logging.error(f"Failed to execute release request for item {item['name']} (ID: {item_uploaded['response']['assetId']}). Check logs.")
                            self.stats.add_failure("Release failed (Request Error)")
                            
            except Exception as e:
                if str(e) == "403":
                    logging.error("403: Could mean invalid cookie.")
                    cookie.generate_token()
                    continue
                logging.error(f"ERROR: {traceback.format_exc()}")
                self.stats.add_failure(str(e))
            finally:
                # Use .get for safe access to sleep time
                sleep_duration = self.config.get("sleep_each_upload", 1)
                if sleep_duration > 0:
                    time.sleep(sleep_duration)

# --- Function to Download Group Assets ---
def download_group_assets(config: Dict, group_id: int, debug_mode: bool):
    """Handles the process of downloading all assets for a specific group."""
    logging.info(f"Starting download process for Group ID: {group_id}")
    
    # Find a valid cookie from the config to use for scraping
    # Need to iterate through the groups config to find any cookie
    auth_cookie_str = None
    if isinstance(config.get("groups"), dict):
        for g_id, g_config in config["groups"].items():
            if isinstance(g_config, dict) and isinstance(g_config.get("uploader_cookies"), list):
                if g_config["uploader_cookies"] and isinstance(g_config["uploader_cookies"][0], str) and g_config["uploader_cookies"][0]:
                    auth_cookie_str = g_config["uploader_cookies"][0]
                    logging.info(f"Using cookie associated with group {g_id} for scraping group {group_id}.")
                    break 
                    
    if not auth_cookie_str:
        logging.error("Could not find a valid .ROBLOSECURITY cookie in config.json under any group. Cannot scrape group assets.")
        return

    try:
        # Initialize cookie object
        cookie_obj = src.cookie.cookie(auth_cookie_str)
    except Exception as e:
        logging.error(f"Failed to initialize cookie object: {e}")
        return

    asset_types = ["classicshirts", "classicpants"]
    all_asset_ids = {} # Store IDs per type

    # Scrape asset IDs
    for asset_type in asset_types:
        logging.info(f"Scraping {asset_type} for Group ID: {group_id}...")
        ids = src.scrape.scrape_group_assets(cookie_obj, str(group_id), asset_type, debug_mode)
        all_asset_ids[asset_type] = ids
        logging.info(f"Found {len(ids)} {asset_type} IDs for Group ID: {group_id}")

    # Fetch details for all found assets to get names
    all_ids_flat = [item_id for sublist in all_asset_ids.values() for item_id in sublist]
    if not all_ids_flat:
        logging.info(f"No clothing assets found for Group ID: {group_id}. Nothing to download.")
        return
        
    logging.info(f"Fetching details for {len(all_ids_flat)} total assets...")
    # Need to fetch details in batches if the list is very large,
    # as the details endpoint might have limits. Let's batch by 100.
    batch_size = 100
    asset_details = {} # Map ID to name
    
    for i in range(0, len(all_ids_flat), batch_size):
        batch_ids = all_ids_flat[i:i+batch_size]
        try:
            # Use a simplified version of sort_assets logic just to get details
            details_response = requests.post(
                "https://catalog.roblox.com/v1/catalog/items/details",
                json={"items": [{"itemType": "Asset", "id": item_id} for item_id in batch_ids]},
                cookies={".ROBLOSECURITY": cookie_obj.cookie},
                headers={"x-csrf-token": cookie_obj.x_token()},
                timeout=20 
            )
            details_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            details_data = details_response.json().get("data", [])
            for item_detail in details_data:
                if item_detail.get("id") and item_detail.get("name"):
                     asset_details[item_detail["id"]] = item_detail["name"]
            logging.info(f"Fetched details batch {i//batch_size + 1}/{len(all_ids_flat)//batch_size + 1}")
            time.sleep(0.5) # Small delay between detail batches
            
        except requests.RequestException as e:
            logging.error(f"Error fetching details batch starting at index {i}: {e}")
            # Decide whether to continue or stop here, maybe skip batch?
            logging.warning("Skipping detail fetching for this batch due to error.")
        except Exception as e:
            logging.error(f"Unexpected error fetching details batch: {e}")
            logging.warning("Skipping detail fetching for this batch due to unexpected error.")

    logging.info(f"Successfully fetched details for {len(asset_details)} assets.")

    # Download assets
    current_directory = os.getcwd()
    download_count = 0
    failed_count = 0

    for asset_type, ids in all_asset_ids.items():
        logging.info(f"Starting download of {len(ids)} {asset_type}...")
        with tqdm(ids, desc=f"Downloading {asset_type}", unit="asset") as pbar:
            for clothing_id in pbar:
                asset_name = asset_details.get(clothing_id)
                if not asset_name:
                    logging.warning(f"Could not find name for asset ID {clothing_id}. Using fallback name.")
                    asset_name = f"unknown_asset_{clothing_id}"
                
                pbar.set_description(f"Downloading {asset_name[:30]}...")
                
                # Replace save_original_asset with save_asset for background removal & sorting
                asset_type_short = "shirts" if asset_type == "classicshirts" else "pants"
                
                # Construct target directory for group downloads
                target_save_dir = os.path.join(current_directory, "src", "assets", "group_downloads", str(group_id), asset_type_short)
                os.makedirs(target_save_dir, exist_ok=True)
                
                saved_path = src.download.save_asset(
                    cookie=cookie_obj, 
                    clothing_id=clothing_id,
                    asset_type=asset_type_short, 
                    asset_name=asset_name,
                    max_score=1.0, # Disable NSFW check for this download step
                    path_2=current_directory, # Base path for temp folder construction
                    config=config, # <-- Pass the config dictionary
                    debug_mode=debug_mode,
                    target_dir=target_save_dir # Specify final save location
                )
                
                # --- Add Log --- 
                if saved_path: 
                    logging.info(f"save_asset returned path: {saved_path}")
                # ------------- 
                
                if saved_path:
                    download_count += 1
                else:
                    failed_count += 1
                    
                # Small sleep to be polite to APIs
                time.sleep(config.get("sleep_each_upload", 0.2)) # Reuse sleep config, default 0.2s

    logging.info(f"Group download complete for Group ID: {group_id}")
    logging.info(f"Successfully downloaded: {download_count} assets")
    logging.info(f"Failed to download: {failed_count} assets")
    input("Press Enter to return to the main menu...") # Simple pause
# --- End Group Download Function ---


# --- Function: Download Keyword Assets ---
def download_keyword_assets(config: Dict, debug_mode: bool):
    """Handles downloading assets based on keywords (Store Only mode), iterating through keywords with limits."""
    logging.info("Starting Keyword Asset Download (Store Only - With Limits)...")
    
    num_to_download_total = 0
    num_per_keyword = None # Initialize as None (meaning no per-keyword limit)

    # --- Get User Input --- 
    try:
        keywords_str = questionary.text(
            "Enter keywords (comma-separated) OR leave blank to use search_keywords.txt:"
        ).ask()
        
        asset_type_choice = questionary.select(
            "Select asset type:",
            choices=[
                questionary.Choice("Shirts Only", value="classicshirts"),
                questionary.Choice("Pants Only", value="classicpants"),
                questionary.Choice("Both Shirts and Pants", value="both")
            ]
        ).ask()
        
        if not asset_type_choice:
             logging.warning("No asset type selected. Aborting.")
             input("Press Enter to return to main menu...")
             return

        # --- Total Download Limit Prompt --- 
        num_total_str = questionary.text(
             "Enter TOTAL number of items to download across all keywords (e.g., 50):",
             validate=lambda text: text.isdigit() and int(text) > 0 or "Please enter a positive number"
        ).ask()
        
        if not num_total_str:
             logging.warning("No total number entered. Aborting.")
             input("Press Enter to return to main menu...")
             return
             
        num_to_download_total = int(num_total_str)

    except KeyboardInterrupt:
        logging.info("Operation cancelled by user.")
        return
    except Exception as e:
        logging.error(f"Error getting input: {e}")
        return

    # --- Prepare Keywords --- 
    if keywords_str:
        search_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        if not search_keywords:
            logging.error("No valid keywords provided.")
            return
        logging.info(f"Using provided keywords: {search_keywords}")
        session_identifier = "_".join(search_keywords)[:50] 
    else:
        logging.info("Loading keywords from search_keywords.txt")
        search_keywords = load_list_from_file("search_keywords.txt")
        if not search_keywords:
            logging.error("search_keywords.txt is empty or not found. Cannot proceed.")
            return
        logging.info(f"Using keywords from file: {len(search_keywords)} keywords found.")
        session_identifier = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    # --- Per-Keyword Limit Prompt (Conditional) --- 
    if len(search_keywords) > 1:
        try:
            num_per_keyword_str = questionary.text(
                 f"Enter max items to download PER keyword (before switching to next, <= {num_to_download_total}):",
                 validate=lambda text: (text.isdigit() and int(text) > 0 and int(text) <= num_to_download_total) or "Enter a number between 1 and {num_to_download_total}"
            ).ask()
            
            if not num_per_keyword_str:
                 logging.warning("No per-keyword limit entered. Aborting.")
                 input("Press Enter to return...")
                 return
                 
            num_per_keyword = int(num_per_keyword_str)
            
        except KeyboardInterrupt:
            logging.info("Operation cancelled by user.")
            return
        except Exception as e:
             logging.error(f"Error getting per-keyword limit input: {e}")
             return
    else:
        # If only one keyword, per-keyword limit is irrelevant (bounded by total)
        num_per_keyword = None 
        
    # --- Find Cookie --- 
    auth_cookie_str = None
    if isinstance(config.get("groups"), dict):
        for g_id, g_config in config["groups"].items():
            if isinstance(g_config, dict) and isinstance(g_config.get("uploader_cookies"), list):
                if g_config["uploader_cookies"] and isinstance(g_config["uploader_cookies"][0], str) and g_config["uploader_cookies"][0]:
                    auth_cookie_str = g_config["uploader_cookies"][0]
                    logging.info(f"Using cookie associated with group {g_id} for scraping.")
                    break
    if not auth_cookie_str:
        logging.error("Could not find a valid cookie in config.json. Cannot scrape.")
        return

    try:
        cookie_obj = src.cookie.cookie(auth_cookie_str)
    except Exception as e:
        logging.error(f"Failed to initialize cookie object: {e}")
        return

    # --- Determine Asset Types to Scrape --- 
    if asset_type_choice == "both":
        asset_types_to_scrape = ["classicshirts", "classicpants"]
    else:
        asset_types_to_scrape = [asset_type_choice]

    # --- Main Download Logic --- 
    downloaded_count = 0 # Overall counter
    failed_count = 0
    processed_ids = set() # Keep track of processed IDs globally
    current_directory = os.getcwd()
    asset_details_cache = {} # Cache details across all keywords

    search_strategy = config.get("search_strategy", { 
        "mode": "random", "limit": 120, "min_price": 5, "max_price": 0
    })
    search_limit_per_req = search_strategy.get("limit", 120)
    
    try:
        # Iterate through each keyword first
        logging.info(f"Processing {len(search_keywords)} keywords for {asset_type_choice} assets (Total limit: {num_to_download_total})...")
        keyword_loop_active = True
        for current_keyword in search_keywords:
            if not keyword_loop_active: break # Exit outer loop if total limit reached
            
            type_loop_active = True
            for current_type in asset_types_to_scrape:
                downloaded_for_this_keyword = 0 # <-- TO HERE
                if not type_loop_active: break # Exit inner type loop if limits reached
                
                logging.info(f"--- Searching for: '{current_keyword}' ({current_type}) [Keyword goal: {num_per_keyword if num_per_keyword else 'N/A'}, Total goal: {num_to_download_total}] ---")
                
                # Prepare search parameters for this specific search
                strategy = search_strategy.get("mode", "random")
                search_params = src.scrape.get_optimal_sort_params(strategy)
                search_params.update({
                    "limit": search_limit_per_req,
                    "minPrice": search_strategy.get("min_price", 5)
                })
                max_price = search_strategy.get("max_price", 0)
                if max_price > 0:
                    search_params["maxPrice"] = max_price
                
                # Scrape assets for the current keyword and type
                item_ids = src.scrape.scrape_assets(
                    cookie_obj, current_keyword, current_type, search_params, debug_mode
                )
                
                if not item_ids:
                    logging.info(f"No items found for '{current_keyword}' ({current_type}).")
                    time.sleep(0.5) 
                    continue # Move to next type or keyword
                
                logging.info(f"Found {len(item_ids)} potential items for '{current_keyword}' ({current_type}).")
                random.shuffle(item_ids)
                
                # Fetch details for newly found IDs (if not cached)
                ids_to_fetch_details = [item_id for item_id in item_ids if item_id not in asset_details_cache]
                if ids_to_fetch_details:
                    # Batch fetch details
                    batch_size = 100
                    logging.info(f"Fetching details for {len(ids_to_fetch_details)} new assets...")
                    for i in range(0, len(ids_to_fetch_details), batch_size):
                         batch_ids = ids_to_fetch_details[i:i+batch_size]
                         try:
                             details_response = requests.post(
                                 "https://catalog.roblox.com/v1/catalog/items/details",
                                 json={"items": [{"itemType": "Asset", "id": item_id} for item_id in batch_ids]},
                                 cookies={".ROBLOSECURITY": cookie_obj.cookie},
                                 headers={"x-csrf-token": cookie_obj.x_token()},
                                 timeout=20
                             )
                             details_response.raise_for_status()
                             details_data = details_response.json().get("data", [])
                             for item_detail in details_data:
                                 if item_detail.get("id") and item_detail.get("name"):
                                     asset_details_cache[item_detail["id"]] = item_detail["name"]
                             time.sleep(0.3)
                         except requests.RequestException as e:
                             logging.error(f"Error fetching details batch: {e}")
                         except Exception as e:
                             logging.error(f"Unexpected error fetching details batch: {e}")

                # Process items found for this specific keyword/type search
                logging.info(f"Processing {len(item_ids)} items found for '{current_keyword}' ({current_type})...")
                with tqdm(item_ids, desc=f"Processing {current_keyword[:20]} ({current_type})", unit="item") as pbar:
                    for clothing_id in pbar:
                        # --- Check Limits --- 
                        if downloaded_count >= num_to_download_total:
                            logging.info("Total download limit reached. Stopping all processing.")
                            type_loop_active = False # Stop processing types for this keyword
                            keyword_loop_active = False # Stop processing further keywords
                            break # Exit inner item loop
                        
                        if num_per_keyword is not None and downloaded_for_this_keyword >= num_per_keyword:
                            logging.info(f"Per-keyword limit ({num_per_keyword}) reached for '{current_keyword}'. Moving to next keyword/type.")
                            break # Exit inner item loop (enough items of this type for this keyword)
                            
                        # --- Process Item --- 
                        if clothing_id in processed_ids:
                            continue # Skip if already processed

                        asset_name = asset_details_cache.get(clothing_id)
                        if not asset_name:
                            logging.warning(f"Could not find name details for asset ID {clothing_id}. Skipping download.")
                            processed_ids.add(clothing_id) 
                            continue
                        
                        # Construct target directory for keyword downloads
                        asset_type_short = "shirts" if current_type == "classicshirts" else "pants"
                        target_save_dir = os.path.join(current_directory, "src", "assets", "keyword_downloads", session_identifier, asset_type_short)
                        os.makedirs(target_save_dir, exist_ok=True)

                        # Call save_asset with the target directory
                        saved_path = src.download.save_asset(
                            cookie=cookie_obj,
                            clothing_id=clothing_id,
                            asset_type=asset_type_short, 
                            asset_name=asset_name,
                            max_score=0.3, 
                            path_2=current_directory, # Base path for temp folder construction
                            config=config, # <-- Pass the config dictionary
                            debug_mode=debug_mode,
                            target_dir=target_save_dir # Specify final save location
                        )
                        
                        processed_ids.add(clothing_id) 
                        
                        if saved_path:
                            downloaded_count += 1 # Increment total count
                            downloaded_for_this_keyword += 1 # Increment keyword count
                        else:
                            failed_count += 1
                            
                        # Small sleep between downloads
                        time.sleep(config.get("sleep_each_upload", 0.1)) 
                # End of item processing loop for this keyword/type
            # End of type loop for this keyword
            if not keyword_loop_active: break # Check again if total limit was hit in inner loop
            
            # Optional: Pause between keywords
            time.sleep(1) 
        # End of keyword loop

    except KeyboardInterrupt:
        logging.info("Keyword download process interrupted by user.")
    except Exception as e:
        logging.error(f"Error during keyword download: {e}")
        if debug_mode:
            logging.error(traceback.format_exc())

    logging.info(f"Keyword download finished.")
    logging.info(f"Target total downloads: {num_to_download_total}")
    logging.info(f"Successfully downloaded: {downloaded_count} unique assets")
    logging.info(f"Failed attempts: {failed_count} assets")
    input("Press Enter to return to the main menu...")

# --- Function: Upload Stored Assets ---
def upload_stored_assets(config: Dict, debug_mode: bool):
    # --- Load Upload Log at the start --- 
    uploaded_set = load_upload_log(UPLOAD_LOG_FILE)
    # ------------------------------------
    
    logging.info("Starting Upload Stored Assets...")
    
    base_asset_path = os.path.join(os.getcwd(), "src", "assets")
    group_dl_path = os.path.join(base_asset_path, "group_downloads")
    keyword_dl_path = os.path.join(base_asset_path, "keyword_downloads")
    
    available_folders = []
    # Scan group downloads
    if os.path.isdir(group_dl_path):
        for group_id_folder in os.listdir(group_dl_path):
            full_path = os.path.join(group_dl_path, group_id_folder)
            if os.path.isdir(full_path):
                available_folders.append(questionary.Choice(f"Group ID: {group_id_folder}", value=full_path))
                
    # Scan keyword downloads
    if os.path.isdir(keyword_dl_path):
         for session_folder in os.listdir(keyword_dl_path):
            full_path = os.path.join(keyword_dl_path, session_folder)
            if os.path.isdir(full_path):
                 # Try to make the display name more readable if it's a timestamp
                 display_name = session_folder
                 try:
                     # Check if it looks like our timestamp format
                     datetime.strptime(session_folder, '%Y%m%d_%H%M%S')
                     display_name = f"Keyword Session: {session_folder}" 
                 except ValueError:
                     display_name = f"Keyword Set: {session_folder}" # Use original name if not timestamp
                     
                 available_folders.append(questionary.Choice(display_name, value=full_path))

    if not available_folders:
        logging.warning("No downloaded asset folders found in src/assets/group_downloads or src/assets/keyword_downloads.")
        input("Press Enter to return to main menu...")
        return
        
    # --- Get User Input --- 
    try:
        source_folder_path = questionary.select(
            "Select the folder containing assets to upload:",
            choices=available_folders + [questionary.Separator(), questionary.Choice("Cancel", value=None)]
        ).ask()
        
        if not source_folder_path:
            logging.info("Upload cancelled.")
            return
            
        # --- Select Target Group and Cookie --- 
        group_choices = []
        group_cookie_map = {}
        if isinstance(config.get("groups"), dict):
            for g_id, g_config in config["groups"].items():
                 if isinstance(g_config, dict) and isinstance(g_config.get("uploader_cookies"), list):
                     if g_config["uploader_cookies"] and g_config["uploader_cookies"][0]:
                         group_choices.append(questionary.Choice(f"Group ID: {g_id}", value=g_id))
                         # Store the first cookie for simplicity
                         group_cookie_map[g_id] = g_config["uploader_cookies"][0]
                         
        if not group_choices:
            logging.error("No valid groups with cookies found in config.json. Cannot upload.")
            input("Press Enter to return...")
            return
            
        target_group_id = questionary.select(
            "Select the target group to upload to:",
            choices=group_choices + [questionary.Separator(), questionary.Choice("Cancel", value=None)]
        ).ask()
        
        if not target_group_id:
            logging.info("Upload cancelled.")
            return
            
        target_cookie_str = group_cookie_map.get(target_group_id)
        if not target_cookie_str:
            # Should not happen if selection was from map keys
            logging.error("Internal error: Could not find cookie for selected group.")
            return

        # --- Upload Options --- 
        use_default_price = questionary.confirm(
             f"Use default price ({config.get('assets_price', 5)} Robux) from config.json?", default=True
        ).ask()
        if use_default_price:
             upload_price = config.get('assets_price', 5)
        else:
             price_str = questionary.text(
                 "Enter upload price (Robux):",
                 validate=lambda text: text.isdigit() and int(text) >= 0 or "Please enter a non-negative number"
             ).ask()
             if not price_str:
                  logging.warning("No price entered. Aborting.")
                  return
             upload_price = int(price_str)
             
        use_default_desc = questionary.confirm(
             f"Use default description (\"{config.get('description', 'shop.')}\") from config.json?", default=True
        ).ask()
        if use_default_desc:
            upload_description = config.get('description', 'shop.')
        else:
            upload_description = questionary.text("Enter asset description:").ask()
            if upload_description is None: # Handle potential cancel
                 logging.warning("No description entered. Aborting.")
                 return
                 
        # Optional NSFW Check before upload?
        perform_nsfw_check = questionary.confirm("Perform NSFW check before uploading? (Recommended)", default=True).ask()
        max_nudity_value = config.get("max_nudity_value", 0.1) if perform_nsfw_check else 1.0 # Effectively disable if not checking

    except KeyboardInterrupt:
        logging.info("Operation cancelled by user.")
        return
    except Exception as e:
        logging.error(f"Error getting input: {e}")
        return

    # --- Initialize Cookie Object --- 
    try:
        cookie_obj = src.cookie.cookie(target_cookie_str)
    except Exception as e:
        logging.error(f"Failed to initialize cookie object: {e}")
        return

    # --- Find Asset Files --- 
    asset_files_to_upload = []
    for root, _, files in os.walk(source_folder_path):
        asset_type_short = os.path.basename(root) # e.g., 'shirts' or 'pants'
        if asset_type_short in ["shirts", "pants"]:
            for file in files:
                if file.lower().endswith(".png"):
                    file_path = os.path.join(root, file)
                    # Stricter Sanitization for upload_name
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    sanitized_name = unidecode(base_name)
                    # 1. Keep only letters, numbers, and spaces
                    sanitized_name = re.sub(r'[^a-zA-Z0-9\s]+', '', sanitized_name)
                    # 2. Collapse multiple spaces to single spaces
                    sanitized_name = re.sub(r'\s+', ' ', sanitized_name)
                    # 3. Strip leading/trailing whitespace
                    sanitized_name = sanitized_name.strip()
                    # 4. NEW: Remove trailing numbers (and any space before them)
                    sanitized_name = re.sub(r'\s*\d+$', '', sanitized_name).strip()
                    # 5. Limit length
                    upload_name = sanitized_name[:50] 
                    
                    # Ensure name is not empty after sanitization
                    if not upload_name:
                        upload_name = f"Default {asset_type_short[:-1].capitalize()} Name" # Fallback name
                        logging.warning(f"Filename '{base_name}' resulted in empty name after sanitization. Using fallback: '{upload_name}'")

                    asset_files_to_upload.append({
                        "path": file_path,
                        "name": upload_name, # Use the new strictly sanitized name
                        "type": asset_type_short
                    })

    if not asset_files_to_upload:
        logging.warning(f"No .png files found in the selected folder structure: {source_folder_path}")
        input("Press Enter to return...")
        return

    logging.info(f"Found {len(asset_files_to_upload)} assets to upload.")
    
    # --- Get User Confirmation and Limit --- 
    total_assets_found = len(asset_files_to_upload)
    num_to_upload = 0
    
    if total_assets_found > 0:
        num_to_upload_str = questionary.text(
            f"Found {total_assets_found} assets. How many do you want to upload? (Enter 0 to cancel):",
            validate=lambda text: (
                text.isdigit() and 0 <= int(text) <= total_assets_found
            ) or f"Please enter a number between 0 and {total_assets_found}"
        ).ask()

        if num_to_upload_str is None or int(num_to_upload_str) == 0:
            logging.info("Upload cancelled by user input.")
            input("Press Enter to return...") # Pause needed here
            return
            
        num_to_upload = int(num_to_upload_str)
        
        # Calculate estimated cost (upload_price is determined earlier)
        estimated_cost = num_to_upload * upload_price 
        
        confirm_upload = questionary.confirm(
            f"Proceed with uploading {num_to_upload} out of {total_assets_found} found assets for an estimated {estimated_cost} Robux?"
        ).ask()
        
        if not confirm_upload:
            logging.info("Upload cancelled by user confirmation.")
            input("Press Enter to return...") # Pause needed here
            return
    else:
        # This case is already handled by the check around line 935, but kept for clarity
        logging.warning("No assets found to upload.")
        input("Press Enter to return...")
        return
        
    # Slice the list to process only the requested number
    asset_files_to_process = asset_files_to_upload[:num_to_upload]
    # --- End Confirmation --- 
    
    # --- Upload Loop --- 
    upload_stats = {"success": 0, "failed_nsfw": 0, "failed_upload": 0, "failed_release": 0, "skipped_uploaded": 0} # Added skipped stat
    try:
        # Iterate over the SLICED list
        with tqdm(asset_files_to_process, desc="Uploading Assets", unit="item") as pbar:
            for asset_info in pbar:
                file_path = asset_info["path"]
                upload_name = asset_info["name"]
                asset_type_short = asset_info["type"]
                pbar.set_description(f"Uploading {upload_name[:30]}...")
                
                # --- CHECK UPLOAD LOG --- 
                image_hash = calculate_file_hash(file_path)
                if not image_hash: # Handle hashing error
                    upload_stats["failed_upload"] += 1 # Count as failed create
                    continue 
                
                # Use target_group_id selected by user for checking
                if (target_group_id, image_hash) in uploaded_set:
                    logging.info(f"Skipping item {upload_name} (Hash: {image_hash[:8]}...): Already uploaded to group {target_group_id}.")
                    upload_stats["skipped_uploaded"] += 1
                    continue
                # --- END CHECK UPLOAD LOG ---
                
                # Optional NSFW Check
                if perform_nsfw_check:
                    try:
                        # Ensure opennsfw2 (n2) is imported if needed
                        nsfw_score = src.download.n2.predict_image(file_path)
                        if nsfw_score > max_nudity_value:
                             logging.warning(f"Asset failed NSFW check: {os.path.basename(file_path)}, Score: {nsfw_score:.2f}. Skipping.")
                             upload_stats["failed_nsfw"] += 1
                             continue
                    except Exception as e:
                        logging.error(f"Error during NSFW check for {os.path.basename(file_path)}: {e}. Skipping.")
                        upload_stats["failed_nsfw"] += 1
                        continue

                # Upload Step 1: Create Asset
                item_uploaded = src.upload.create_asset(
                    upload_name, # Use the strictly sanitized name
                    file_path, 
                    asset_type_short,
                    cookie_obj, 
                    target_group_id,
                    config["description"], # Use config description 
                    _total_tries=5, 
                    wait_time=5 
                )
                
                if item_uploaded is False:
                    logging.error(f"Failed to create asset: {upload_name}. Check logs.")
                    upload_stats["failed_upload"] += 1
                    continue # Try next file
                elif item_uploaded == 2:
                    logging.error(f"Failed to upload {upload_name} (Insufficient Funds). Skipping remaining uploads.")
                    upload_stats["failed_upload"] += 1
                    break # Stop if out of funds
                elif item_uploaded == 3:
                    logging.error(f"Failed to upload {upload_name} (No Permission). Check cookie/group. Skipping.")
                    upload_stats["failed_upload"] += 1
                    continue # Try next file

                # Upload Step 2: Release Asset
                try:
                    asset_id = item_uploaded['response']['assetId']
                    response = src.upload.release_asset(
                        cookie_obj, 
                        asset_id, # Use the extracted asset ID
                        upload_price, 
                        upload_name, # Use sanitized name again for release
                        config["description"], # Use description directly from config
                        target_group_id
                    )
                    # Check the response object returned by release_asset
                    if response and response.status_code == 200:
                        try:
                            response_json = response.json()
                            if response_json.get("status") == 0:
                                logging.info(f"Successfully uploaded and released: {upload_name} (ID: {asset_id})")
                                upload_stats["success"] += 1
                                
                                # --- APPEND TO UPLOAD LOG ON SUCCESS --- 
                                append_to_upload_log(UPLOAD_LOG_FILE, target_group_id, image_hash)
                                uploaded_set.add((target_group_id, image_hash)) # Update in-memory set
                                # ---------------------------------------
                            else:
                                # Handle non-zero status in JSON
                                logging.error(f"Failed to release item {upload_name} (ID: {asset_id}). Status: {response.status_code}, Response: {response.text}")
                                upload_stats["failed_release"] += 1
                        except json.JSONDecodeError:
                            logging.error(f"Failed to decode release response for item {upload_name} (ID: {asset_id}). Status: {response.status_code}, Response: {response.text}")
                            upload_stats["failed_release"] += 1
                    elif response:
                        # Handle non-200 status code from release_asset
                        logging.error(f"Failed to release item {upload_name} (ID: {asset_id}). Status: {response.status_code}, Response: {response.text}")
                        upload_stats["failed_release"] += 1
                    else:
                        # Handle case where release_asset returned None
                        logging.error(f"Failed to execute release request for item {upload_name} (ID: {asset_id}). Check logs.")
                        upload_stats["failed_release"] += 1
                except KeyError:
                     # Handle case where 'response' or 'assetId' is missing in item_uploaded
                     logging.error(f"Error extracting assetId after creating asset {upload_name}. Response from create_asset: {item_uploaded}")
                     upload_stats["failed_release"] += 1 # Count as release failure
                except Exception as e:
                     # Log the asset ID correctly if release fails, handle potential errors during ID extraction
                     asset_id_for_log = item_uploaded.get('response', {}).get('assetId', 'N/A') # Safely get ID for logging
                     logging.error(f"Error releasing asset {upload_name} (Created ID: {asset_id_for_log}): {e}") 
                     upload_stats["failed_release"] += 1
                     
                # Small sleep
                time.sleep(config.get("sleep_each_upload", 1)) # Reuse sleep config

    except KeyboardInterrupt:
        logging.info("Upload process interrupted by user.")
    except Exception as e:
        logging.error(f"Error during bulk upload: {e}")
        if debug_mode:
            logging.error(traceback.format_exc())

    # --- Final Summary --- 
    logging.info("Stored asset upload finished.")
    logging.info(f"Successfully uploaded: {upload_stats['success']} assets")
    logging.info(f"Skipped (Already Uploaded): {upload_stats['skipped_uploaded']} assets") # Added skipped stat
    logging.info(f"Failed (NSFW): {upload_stats['failed_nsfw']} assets")
    logging.info(f"Failed (Create): {upload_stats['failed_upload']} assets")
    logging.info(f"Failed (Release): {upload_stats['failed_release']} assets")
    input("Press Enter to return to the main menu...")

# --- End Upload Function ---


# --- Function: Edit Settings --- 
def edit_settings(config: Dict, config_path: str):
    """Allows the user to edit configuration settings via the CLI."""
    logging.info("Current Settings:")
    # Print a subset of current settings for context (add more as needed)
    print(f"  Asset Price: {config.get('assets_price', 'Not Set')}")
    print(f"  Description: {config.get('description', 'Not Set')}")
    print(f"  Sleep (Upload): {config.get('sleep_each_upload', 'Not Set')}")
    # Add other relevant settings here
    print("---")

    while True:
        setting_choice = questionary.select(
            "Which setting category would you like to edit?",
            choices=[
                questionary.Choice("Asset Price", value="price"),
                questionary.Choice("Asset Description", value="desc"),
                questionary.Choice("Upload Sleep Duration", value="sleep"),
                questionary.Choice("Duplicate Check Enabled", value="dupe_check"),
                questionary.Choice("Manage Group Cookies", value="groups"),
                questionary.Choice("Custom Watermark Settings", value="watermark"),
                # Add more categories here (e.g., "Search Strategy")
                questionary.Separator(),
                questionary.Choice("Save and Exit", value="save"),
                questionary.Choice("Exit Without Saving", value="exit")
            ]
        ).ask()

        if setting_choice == "price":
            new_price_str = questionary.text(
                f"Enter new asset price (current: {config.get('assets_price', 5)}):",
                validate=lambda text: text.isdigit() and int(text) >= 0 or "Please enter a non-negative number"
            ).ask()
            if new_price_str is not None:
                config['assets_price'] = int(new_price_str)
                logging.info(f"Asset price updated to: {config['assets_price']}")
            else:
                 logging.warning("Price change cancelled.")

        elif setting_choice == "desc":
            new_desc = questionary.text(
                f"Enter new asset description (current: \"{config.get('description', 'shop.')}\"):",
            ).ask()
            if new_desc is not None:
                config['description'] = new_desc
                logging.info(f"Asset description updated to: \"{config['description']}\"")
            else:
                 logging.warning("Description change cancelled.")
                 
        elif setting_choice == "sleep":
            new_sleep_str = questionary.text(
                f"Enter new sleep duration between uploads (seconds, current: {config.get('sleep_each_upload', 1.0)}):",
                validate=lambda text: (
                    text.replace('.', '', 1).isdigit() and float(text) >= 0 
                    or "Please enter a non-negative number (e.g., 0.5, 1, 2.0)"
                )
            ).ask()
            if new_sleep_str is not None:
                config['sleep_each_upload'] = float(new_sleep_str)
                logging.info(f"Upload sleep duration updated to: {config['sleep_each_upload']}s")
            else:
                logging.warning("Sleep duration change cancelled.")
                
        elif setting_choice == "dupe_check":
            # Assuming default is True if not present in config
            current_status = config.get('dupe_check', True) 
            enable_dupe_check = questionary.confirm(
                f"Enable duplicate checking? (current: {'Enabled' if current_status else 'Disabled'})",
                default=current_status
            ).ask()
            
            if enable_dupe_check is not None: # Check if user cancelled
                config['dupe_check'] = enable_dupe_check
                logging.info(f"Duplicate checking set to: {'Enabled' if config['dupe_check'] else 'Disabled'}")
            else:
                logging.warning("Duplicate check setting change cancelled.")

        elif setting_choice == "groups":
            manage_group_cookies(config)

        elif setting_choice == "watermark":
            # Ensure the watermark config section exists
            if "custom_watermark" not in config:
                 config["custom_watermark"] = {
                     "enabled": False, "text": "MyBrand", "font_path": "arial.ttf",
                     "font_size": 14, "position": "bottom_center", "color": [255, 255, 255, 128]
                 }
            wm_config = config["custom_watermark"]

            while True:
                wm_choice = questionary.select(
                    "Edit Custom Watermark Settings:",
                    choices=[
                        questionary.Choice(f"Enabled: {'Yes' if wm_config.get('enabled', False) else 'No'}", value="enabled"),
                        questionary.Choice(f"Text: \"{wm_config.get('text', '')}\"", value="text"),
                        questionary.Choice(f"Font Path: {wm_config.get('font_path', 'arial.ttf')}", value="font"),
                        questionary.Choice(f"Font Size: {wm_config.get('font_size', 14)}", value="size"),
                        questionary.Choice(f"Position: {wm_config.get('position', 'bottom_center')}", value="position"),
                        questionary.Choice(f"Color (RGBA): {wm_config.get('color', [255,255,255,128])}", value="color"),
                        questionary.Separator("--- Area Replacement --- "),
                        questionary.Choice(f"Replace Specific Area: {'Yes' if wm_config.get('replace_area_enabled', False) else 'No'}", value="replace_toggle"),
                        questionary.Choice(f"Area Background Color (RGB): {wm_config.get('replace_area_color', [0,0,0])}", value="replace_color"),
                        questionary.Choice(f"Area Text Color (RGBA): {wm_config.get('text_color_override', [255,255,255,255])}", value="replace_text_color"),
                        questionary.Separator(),
                        questionary.Choice("Back to Main Settings", value="back")
                    ]
                ).ask()

                if wm_choice == "enabled":
                    wm_config['enabled'] = questionary.confirm(f"Enable custom watermark?", default=wm_config.get('enabled', False)).ask()
                    logging.info(f"Watermark enabled: {wm_config['enabled']}")
                elif wm_choice == "text":
                    new_text = questionary.text("Enter new watermark text:", default=wm_config.get('text', 'MyBrand')).ask()
                    if new_text is not None: wm_config['text'] = new_text
                elif wm_choice == "font":
                    # Add validation for file existence if needed
                    new_font = questionary.text("Enter font path (e.g., C:/Windows/Fonts/arial.ttf or just arial.ttf):", default=wm_config.get('font_path', 'arial.ttf')).ask()
                    if new_font is not None: wm_config['font_path'] = new_font
                    logging.info("Note: Ensure the font path is correct and accessible.")
                elif wm_choice == "size":
                    new_size_str = questionary.text("Enter font size:", default=str(wm_config.get('font_size', 14)), validate=lambda s: s.isdigit() and int(s) > 0 or "Enter a positive number").ask()
                    if new_size_str is not None: wm_config['font_size'] = int(new_size_str)
                elif wm_choice == "position":
                     # Example positions, could add more
                    new_pos = questionary.select("Select watermark position:", choices=["bottom_center", "bottom_left", "bottom_right", "top_center"], default=wm_config.get('position', 'bottom_center')).ask()
                    if new_pos is not None: wm_config['position'] = new_pos
                elif wm_choice == "color":
                    new_color_str = questionary.text("Enter RGBA color (e.g., 255,255,255,128):", default=",".join(map(str, wm_config.get('color', [255,255,255,128]))), validate=lambda s: len(s.split(',')) == 4 and all(p.strip().isdigit() and 0 <= int(p.strip()) <= 255 for p in s.split(',')) or "Enter 4 numbers (0-255) separated by commas").ask()
                    if new_color_str is not None: wm_config['color'] = [int(p.strip()) for p in new_color_str.split(',')]
                
                elif wm_choice == "replace_toggle":
                    wm_config['replace_area_enabled'] = questionary.confirm("Enable replacing specific area for watermark?", default=wm_config.get('replace_area_enabled', False)).ask()
                    logging.info(f"Replace area enabled: {wm_config['replace_area_enabled']}")
                    if wm_config['replace_area_enabled']:
                         logging.info(f"Ensure 'replace_area_coords' in config.json are measured and set correctly: {wm_config.get('replace_area_coords', 'Not Set!')}")
                
                elif wm_choice == "replace_color":
                    new_replace_color_str = questionary.text("Enter RGB background color for replaced area (e.g., 0,0,0):", default=",".join(map(str, wm_config.get('replace_area_color', [0,0,0]))), validate=lambda s: len(s.split(',')) == 3 and all(p.strip().isdigit() and 0 <= int(p.strip()) <= 255 for p in s.split(',')) or "Enter 3 numbers (0-255) separated by commas").ask()
                    if new_replace_color_str is not None: wm_config['replace_area_color'] = [int(p.strip()) for p in new_replace_color_str.split(',')]

                elif wm_choice == "replace_text_color":
                    new_replace_text_color_str = questionary.text("Enter RGBA text color for replaced area (e.g., 255,255,255,255):", default=",".join(map(str, wm_config.get('text_color_override', [255,255,255,255]))), validate=lambda s: len(s.split(',')) == 4 and all(p.strip().isdigit() and 0 <= int(p.strip()) <= 255 for p in s.split(',')) or "Enter 4 numbers (0-255) separated by commas").ask()
                    if new_replace_text_color_str is not None: wm_config['text_color_override'] = [int(p.strip()) for p in new_replace_text_color_str.split(',')]

                elif wm_choice == "back" or wm_choice is None:
                    break # Exit watermark settings sub-menu

        elif setting_choice == "save":
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4) # Use indent for readability
                logging.info(f"Settings saved successfully to {config_path}")
                break # Exit the settings loop
            except Exception as e:
                logging.error(f"Failed to save settings to {config_path}: {e}")
                # Optionally ask if user wants to retry or exit without saving
                if not questionary.confirm("Saving failed. Exit without saving anyway?", default=False).ask():
                    continue # Go back to menu
                else:
                    break # Exit loop despite save failure
                    
        elif setting_choice == "exit" or setting_choice is None:
            # Ask for confirmation if changes were made (optional, requires tracking changes)
            logging.info("Exiting settings editor without saving.")
            break # Exit the settings loop

# --- End Settings Function ---

# --- Helper Function: Manage Group Cookies --- 
def manage_group_cookies(config: Dict):
    """Provides a sub-menu to manage group IDs and their cookies."""
    if 'groups' not in config or not isinstance(config['groups'], dict):
        logging.error("'groups' section not found or invalid in config.json.")
        config['groups'] = {} # Initialize if missing
        logging.info("Initialized empty 'groups' section.")

    while True:
        # Prepare choices: list existing groups + actions
        group_choices = [
            questionary.Choice(f"Group ID: {gid} (Cookie: ...{data.get('uploader_cookies', ['N/A'])[0][-20:] if data.get('uploader_cookies') else 'None'})", value=gid) 
            for gid, data in config.get('groups', {}).items()
        ]
        
        action_choices = [
             questionary.Separator("--- Actions ---"),
             questionary.Choice("Add/Update Cookie for Group", value="add_update"),
             # questionary.Choice("Remove Cookie from Group", value="remove_cookie"), # TODO
             # questionary.Choice("Remove Entire Group", value="remove_group"), # TODO
             questionary.Separator(),
             questionary.Choice("Back to Main Settings", value="back")
        ]

        group_action = questionary.select(
            "Select Group to view/modify or choose an action:",
            choices= group_choices + action_choices
        ).ask()

        if group_action == "back" or group_action is None:
            break # Exit group management sub-menu
            
        elif group_action == "add_update":
            group_id_to_edit = questionary.text(
                "Enter Group ID to add or update cookie for:",
                validate=lambda text: text.isdigit() or "Group ID must be numeric"
            ).ask()
            
            if not group_id_to_edit:
                logging.warning("Add/Update cancelled.")
                continue

            new_cookie = questionary.text(
                 "Paste the full .ROBLOSECURITY cookie:",
                 validate=lambda text: (
                     # Option 1: Check for the full format with warning
                     (isinstance(text, str) and
                      text.startswith('_|WARNING:') and
                      '|_' in text and
                      text.rfind('|_') > text.find('_|WARNING:') and
                      len(text.split('|_')[-1]) > 100) # Check length of actual cookie part
                     or
                     # Option 2: Check for just the cookie value (long string, no warning)
                     (isinstance(text, str) and
                      not text.startswith('_|WARNING:') and
                      len(text) > 100) # Assume cookie value itself is long
                 ) or "Invalid format. Paste either the full cookie (starting with '_|WARNING:...') or just the cookie value itself (the long string after '|_')."
            ).ask()
            
            if not new_cookie:
                 logging.warning("Cookie entry cancelled.")
                 continue

            # Ensure the group exists in the config structure
            if group_id_to_edit not in config['groups']:
                 config['groups'][group_id_to_edit] = {} # Create group entry if new
            
            # Update or set the first cookie in the list
            config['groups'][group_id_to_edit]['uploader_cookies'] = [new_cookie]
            logging.info(f"Cookie updated for Group ID: {group_id_to_edit}")

        # TODO: Add elif blocks for remove_cookie, remove_group
            
        # If a Group ID was selected directly (future enhancement for viewing/quick actions?)
        # elif group_action in config.get('groups', {}):
        #     logging.info(f"Selected Group {group_action}, add specific actions here later.")
        #     pass 

# --- End Group Cookie Helper ---


# --- Utility to clear screen ---
def clear_screen():
    """Clears the terminal screen."""
    command = 'cls' if platform.system().lower() == "windows" else 'clear'
    os.system(command)
# --- End Utility ---


# --- Main Execution Block ---
if __name__ == "__main__":
    # Initialize colorama
    init(autoreset=True) # Autoreset colors after each print

    # --- Logging Setup --- 
    # (Existing logging setup remains here) ...
    # Basic logging setup (gets overwritten by the handler setup below, but sets the level)
    logging.basicConfig(level=log_level)

    # Create formatter and handler
    log_formatter = ColoredFormatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    # Get the root logger and remove existing handlers to avoid duplicate logs
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    # Add our custom handler
    root_logger.addHandler(console_handler)
    # Set the level on the root logger itself
    root_logger.setLevel(log_level)

    # --- Add File Handler for Debug Mode ---
    if args.debug:
        try:
            log_filename = 'debug.log'
            # Create a FileHandler, overwrite file each run ('w')
            file_handler = logging.FileHandler(log_filename, mode='w', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG) # Log all debug messages to the file

            # Create a standard Formatter for the file log
            file_formatter = logging.Formatter(
                fmt='%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s', # Detailed format
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)

            # Add the FileHandler to the root logger
            root_logger.addHandler(file_handler)
            # Log confirmation to console (and potentially the file itself)
            logging.info(f"Debug mode active. Logging detailed output to: {log_filename}")
        except Exception as e:
            # Log error to console if file logging setup fails
            logging.error(f"Failed to set up debug file logging to {log_filename}: {e}")
    # --- End File Handler Setup ---

    # Configure TensorFlow logger level separately (after setting up root logger)
    if args.debug:
        tensorflow.get_logger().setLevel(logging.WARNING)
    else:
        tensorflow.get_logger().setLevel(logging.FATAL)

    # --- Load Config --- 
    config = None
    try:
        config_path = args.config
        logging.info(f"Loading config from: {config_path}")
        with open(config_path, "r", encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}. Exiting.")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Error decoding config file {config_path}: {e}. Exiting.")
        exit(1)
    except Exception as e:
        print(f"ERROR: Error reading config file {config_path}: {e}. Exiting.")
        exit(1)
            
    if not config:
        print("ERROR: Failed to load configuration. Exiting.")
        exit(1)

    # --- Main Interactive Loop ---
    while True:
        clear_screen()
        print(Fore.MAGENTA + Style.BRIGHT + "=== Xool - Roblox Clothing Bot ===\n")
        
        choice = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice("Download Group Assets (Store Only)", value="group_dl"),
                questionary.Choice("Download Keyword Assets (Store Only)", value="keyword_dl"),
                questionary.Choice("Upload Stored Assets", value="upload"),
                questionary.Choice("Run Automatic Upload (Original Mode)", value="auto"),
                questionary.Separator(),
                questionary.Choice("Edit Settings", value="settings"),
                questionary.Choice("Exit", value="exit")
            ],
            use_shortcuts=True
        ).ask() # Use ask() to get the result

        if choice == "group_dl":
            clear_screen()
            try:
                group_id_str = questionary.text("Enter the Group ID to download assets from:").ask()
                if group_id_str and group_id_str.isdigit():
                    group_id = int(group_id_str)
                    download_group_assets(config, group_id, args.debug)
                else:
                    print(Fore.RED + "Invalid Group ID entered.")
                    input("Press Enter to continue...")
            except KeyboardInterrupt:
                logging.info("Operation cancelled by user.")
            except Exception as e:
                logging.error(f"Error during group download: {e}")
                if args.debug:
                    logging.error(traceback.format_exc())
                input("Press Enter to continue...")
                
        elif choice == "keyword_dl":
            clear_screen()
            download_keyword_assets(config, args.debug)
            
        elif choice == "upload":
            clear_screen()
            upload_stored_assets(config, args.debug)
            
        elif choice == "auto":
            clear_screen()
            logging.info("Starting Automatic Upload Mode...")
            try:
                # Load keywords and blacklist only needed for this mode
                logging.info("Loading keywords from search_keywords.txt")
                loaded_keywords = load_list_from_file("search_keywords.txt")
                logging.info(f"Loaded {len(loaded_keywords)} keywords.")
                
                logging.info("Loading blacklist from blacklisted_words.txt")
                loaded_blacklist = load_list_from_file("blacklisted_words.txt")
                logging.info(f"Loaded {len(loaded_blacklist)} blacklisted words.")

                # Start xool upload process
                xool_instance = xool(config, loaded_keywords, loaded_blacklist)
                # The xool __init__ handles the process and prints stats
                
            except KeyboardInterrupt:
                logging.info("Automatic Upload process interrupted by user.")
            except Exception as e:
                logging.error(f"Fatal error during automatic upload process: {str(e)}")
                if args.debug:
                    logging.error(traceback.format_exc())
            if args.debug: 
                 input("Automatic Upload finished or was interrupted. Press Enter to return to the main menu...")
        
        # --- Add Settings Block --- 
        elif choice == "settings":
            clear_screen()
            logging.info("Entering settings editor...")
            # Pass the loaded config and its path to the editor function
            edit_settings(config, config_path) 
            logging.info("Exiting settings editor.")
            # Optionally pause here too
            input("Press Enter to return to the main menu...")
            
        # -------------------------
        elif choice == "exit" or choice is None: # Handle Escape/Ctrl+C
            print(Fore.YELLOW + "Exiting Xool. Goodbye!")
            break
        else:
            # Should not happen with questionary select
            print(Fore.RED + "Invalid choice.")
            time.sleep(1)

    # --- End of Main Loop ---
    logging.info("Xool application closed.")

    # Removed the old argument-based logic
    # --- Mode Selection: Group Download or Standard Upload ---
    # if args.group_id and args.download_only:
    #     # --- Group Download Mode ---
    #     ...
    # elif not args.group_id:
    #     # --- Standard Upload Mode ---
    #     ...
    # else:
    #      # Handle invalid argument combinations
    #      ...

    # logging.info("Xool process finished.")

