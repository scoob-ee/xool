import os
from PIL import Image, ImageDraw, ImageFont
import imagehash
import re
import numpy as np
from functools import lru_cache
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, Optional
import threading
import json # Needed for log handling
import sys, requests, hashlib
import traceback


# --- Upload Log Constants ---
UPLOAD_LOG_DIR = os.path.join(os.getcwd(), "src", "assets", "upload_logs")
os.makedirs(UPLOAD_LOG_DIR, exist_ok=True)

# --- Upload Log Handling Functions ---
def get_upload_log_path(group_id: str) -> str:
    """Generates the path for a group's upload log file."""
    return os.path.join(UPLOAD_LOG_DIR, f"{group_id}_log.json")

def load_upload_log(group_id: str) -> set:
    """Loads the set of uploaded pHashes for a specific group."""
    log_path = get_upload_log_path(group_id)
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                # Load hashes as strings, return as a set for fast lookups
                return set(json.load(f))
        except json.JSONDecodeError:
            logging.error(f"Error decoding upload log file: {log_path}. Treating as empty.")
            return set()
        except Exception as e:
            logging.error(f"Error loading upload log file {log_path}: {e}. Treating as empty.")
            return set()
    return set() # Return empty set if log doesn't exist

def save_upload_log(group_id: str, uploaded_hashes: set):
    """Saves the set of uploaded pHashes for a specific group."""
    log_path = get_upload_log_path(group_id)
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            # Convert set to list for JSON serialization
            json.dump(list(uploaded_hashes), f)
    except Exception as e:
        logging.error(f"Error saving upload log file {log_path}: {e}")

def check_if_uploaded(image_path: str, target_group_id: str) -> bool:
    """Checks if an image (by pHash) has already been uploaded to the target group."""
    try:
        img = Image.open(image_path)
        img_phash = str(imagehash.phash(img)) # Calculate and convert phash to string
    except Exception as e:
        logging.error(f"Could not calculate pHash for {os.path.basename(image_path)}: {e}. Assuming not uploaded.")
        return False

    uploaded_hashes = load_upload_log(target_group_id)
    return img_phash in uploaded_hashes

def add_to_upload_log(image_path: str, target_group_id: str):
    """Adds an image's pHash to the target group's upload log."""
    try:
        img = Image.open(image_path)
        img_phash = str(imagehash.phash(img)) # Calculate and convert phash to string
    except Exception as e:
        logging.error(f"Could not calculate pHash for {os.path.basename(image_path)}: {e}. Cannot add to log.")
        return
        
    uploaded_hashes = load_upload_log(target_group_id)
    if img_phash not in uploaded_hashes:
        uploaded_hashes.add(img_phash)
        save_upload_log(target_group_id, uploaded_hashes)
        logging.debug(f"Added pHash {img_phash} to upload log for group {target_group_id}.")
    else:
         logging.debug(f"pHash {img_phash} already in upload log for group {target_group_id}.")

# --- End Upload Log Handling ---


def is_duplicate_file(folder_path, filename):
    pattern = re.compile(r"^(.*?)(_\d+)?(\.[^.]*)?$")
    match = pattern.match(filename)

    if not match:
        return False

    base_name = match.group(1) + (match.group(3) or "")
    for existing_file in os.listdir(folder_path):
        existing_match = pattern.match(existing_file)
        existing_base_name = existing_match.group(1) + (existing_match.group(3) or "")
        if base_name == existing_base_name and existing_file != filename:
            return True
    return False

def remove_png(path=os.getcwd()):
    """Removes all PNG files except template.png and logobg.png"""
    for root, dirs, files in os.walk(path):
        if 'template' in root:
            continue

        for file in files:
            if file.endswith('.png'):
                file_path = os.path.join(root, file)
                
                try:
                    os.remove(file_path)
                    logging.info(f"Deleted: {file_path}")
                except Exception as e:
                    logging.error(f"Failed to delete {file_path}. Reason: {e}")
                    
def is_similar(new_image_path, folder_path, threshold=1, debug_mode=False):
    folder_path = {"classicshirts": "src/assets/shirts", "classicpants": "src/assets/pants"}[folder_path]
    new_image_hash = imagehash.phash(Image.open(new_image_path))
    new_image_name = os.path.basename(new_image_path)
    for filename in os.listdir(folder_path):
        image_path = os.path.join(folder_path, filename)
        if filename == new_image_name:
            continue
        if os.path.isfile(image_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            folder_image_hash = imagehash.phash(Image.open(image_path))
            hash_diff = new_image_hash - folder_image_hash
            if hash_diff < threshold:
                if debug_mode:
                    logging.debug(f"Hash difference: {hash_diff} (threshold: {threshold})")
                    logging.debug(f"New hash: {new_image_hash}, Existing hash: {folder_image_hash}")
                logging.info(f"{new_image_name} duped by {filename}")
                return True
    return False

# Thread-safe cache for image hashes
class ThreadSafeCache:
    def __init__(self, maxsize=128):
        self.cache = {}
        self.lock = threading.Lock()
        self.maxsize = maxsize
        
    def get(self, key):
        with self.lock:
            return self.cache.get(key)
            
    def set(self, key, value):
        with self.lock:
            if len(self.cache) >= self.maxsize:
                # Remove oldest item
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = value

# Global cache instance
hash_cache = ThreadSafeCache(maxsize=128)

def calculate_image_hashes(image_path: str) -> Optional[Dict[str, imagehash.ImageHash]]:
    """Calculate multiple hash types for an image with caching."""
    # Check cache first
    cached = hash_cache.get(image_path)
    if cached:
        return cached
        
    try:
        img = Image.open(image_path)
        hashes = {
            'phash': imagehash.phash(img),
            'dhash': imagehash.dhash(img),
            'ahash': imagehash.average_hash(img),
            'whash': imagehash.whash(img),
            'colorhash': imagehash.colorhash(img, binbits=3)
        }
        # Store in cache
        hash_cache.set(image_path, hashes)
        return hashes
    except Exception as e:
        logging.error(f"Error calculating hashes for {image_path}: {e}")
        return None

def parallel_hash_calculation(image_paths: list, max_workers: int = 4) -> Dict[str, Dict]:
    """Calculate hashes for multiple images in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(calculate_image_hashes, path): path 
            for path in image_paths
        }
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                hashes = future.result()
                if hashes:
                    results[path] = hashes
            except Exception as e:
                logging.error(f"Error processing {path}: {e}")
    return results

def advanced_similarity_check(new_image_path: str, 
                            folder_path: str,
                            thresholds: Dict[str, int] = {
                                'phash': 3,
                                'dhash': 3,
                                'ahash': 5,
                                'whash': 3,
                                'colorhash': 4
                            },
                            min_matches: int = 2,
                            max_workers: int = 4,
                            debug_mode: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Advanced similarity detection using parallel processing.
    """
    folder_path = {"classicshirts": "src/assets/shirts", "classicpants": "src/assets/pants"}[folder_path]
    new_image_name = os.path.basename(new_image_path)
    
    if debug_mode:
        logging.debug(f"Running parallel similarity check on {new_image_name}")
        
    # Get all valid image paths
    image_paths = [
        os.path.join(folder_path, f) for f in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, f)) 
        and f.lower().endswith(('.png', '.jpg', '.jpeg'))
        and f != new_image_name
    ]
    
    # Calculate new image hashes
    new_hashes = calculate_image_hashes(new_image_path)
    if not new_hashes:
        return False, None
        
    # Calculate hashes for all images in parallel
    existing_hashes = parallel_hash_calculation(image_paths, max_workers)
    
    best_match = None
    best_match_score = 0
    
    for image_path, hashes in existing_hashes.items():
        match_count = 0
        similarity_scores = {}
        
        for hash_type in thresholds:
            if hash_type in new_hashes and hash_type in hashes:
                hash_distance = new_hashes[hash_type] - hashes[hash_type]
                similarity_scores[hash_type] = hash_distance
                if hash_distance < thresholds[hash_type]:
                    match_count += 1
                    
        if debug_mode and match_count > 0:
            logging.debug(f"Match with {os.path.basename(image_path)}: {match_count}/{len(thresholds)} algorithms")
            logging.debug(f"Hash distances: {similarity_scores}")
        
        if match_count >= min_matches:
            weighted_score = sum(1.0 / (1 + s) for s in similarity_scores.values())
            if not best_match or weighted_score > best_match_score:
                best_match = os.path.basename(image_path)
                best_match_score = weighted_score
    
    if best_match:
        message = f"{new_image_name} is similar to {best_match} (matched by {best_match_score:.2f} score)"
        if not debug_mode:
            logging.info(message)
        else:
            logging.debug(message)
        return True, best_match
        
    return False, None

def detect_duplicate(new_image_path, folder_path, use_advanced=True, debug_mode=False):
    """
    Main function to detect duplicates, combining filename check and similarity check.
    
    Parameters:
    - new_image_path: Path to the new image
    - folder_path: 'classicshirts' or 'classicpants'
    - use_advanced: Whether to use the advanced similarity detection
    - debug_mode: Whether to print debug info
    
    Returns:
    - (bool, str): (is_duplicate, reason)
    """
    actual_folder_path = {"classicshirts": "src/assets/shirts", "classicpants": "src/assets/pants"}[folder_path]
    filename = os.path.basename(new_image_path)
    
    if debug_mode:
        logging.debug(f"Checking for duplicates: {filename} in {folder_path}")
    
    # Check for visual similarity
    if use_advanced:
        is_similar, similar_file = advanced_similarity_check(new_image_path, folder_path, debug_mode=debug_mode)
        if is_similar:
            return True, f"visual_similarity:{similar_file}"
    else:
        if is_similar(new_image_path, folder_path, debug_mode=debug_mode):
            return True, "visual_similarity"
    
    return False, None

# --- Function to Apply Custom Watermark ---

def apply_custom_watermark(image_path: str, config: Dict) -> bool:
    """Applies a custom text watermark based on config settings.

    Args:
        image_path: Path to the image file to modify.
        config: The watermark configuration dictionary.

    Returns:
        True if watermark was applied successfully, False otherwise.
    """
    if not config.get('enabled', False):
        return True # Feature not enabled, count as success

    # General settings
    text = config.get('text', 'MyBrand')
    font_path = config.get('font_path', 'arial.ttf')
    font_size = config.get('font_size', 14)
    general_position = config.get('position', 'bottom_center')
    general_color = tuple(config.get('color', [255, 255, 255, 128]))

    # Area replacement settings
    replace_area_enabled = config.get('replace_area_enabled', False)
    replace_coords = config.get('replace_area_coords', [])
    replace_bgcolor = tuple(config.get('replace_area_color', [0, 0, 0])) # RGB
    replace_textcolor = tuple(config.get('text_color_override', general_color)) # RGBA, defaults to general color

    if not os.path.exists(image_path):
        logging.error(f"[Watermark] Image not found: {image_path}")
        return False

    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size

        # Load font (common to both modes)
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            logging.warning(f"[Watermark] Font '{font_path}' not found. Trying default font.")
            try:
                font = ImageFont.load_default()
            except IOError:
                logging.error("[Watermark] Default font not found. Cannot add watermark text.")
                return False

        # --- Determine Text Position and Color --- 
        final_x, final_y = 0, 0
        final_color = general_color

        if replace_area_enabled and len(replace_coords) == 4:
            logging.debug("[Watermark] Using area replacement mode.")
            x0, y0, x1, y1 = replace_coords
            # Ensure coordinates are within bounds
            x0 = max(0, min(x0, img_width))
            y0 = max(0, min(y0, img_height))
            x1 = max(x0, min(x1, img_width))
            y1 = max(y0, min(y1, img_height))
            
            if x0 >= x1 or y0 >= y1:
                 logging.error(f"[Watermark] Invalid replace_area_coords: {replace_coords}. Skipping replacement.")
                 replace_area_enabled = False # Fallback to general positioning
            else:
                # 1. Draw the background rectangle
                logging.debug(f"[Watermark] Drawing background rect at {(x0, y0, x1, y1)} with color {replace_bgcolor}")
                # For solid RGB color, we just need to provide it directly to rectangle
                draw.rectangle([x0, y0, x1, y1], fill=replace_bgcolor)

                # 2. Calculate text position centered within the rectangle
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except AttributeError:
                    try:
                         text_width, text_height = draw.textsize(text, font=font)
                    except AttributeError:
                         logging.error("[Watermark] Cannot determine text size. Cannot center text in area.")
                         # Just save the image with the colored box
                         img.save(image_path, "PNG")
                         return True
                
                rect_width = x1 - x0
                rect_height = y1 - y0
                final_x = x0 + (rect_width - text_width) // 2
                final_y = y0 + (rect_height - text_height) // 2
                final_color = replace_textcolor # Use the override color
                logging.debug(f"[Watermark] Calculated text position within area: ({final_x}, {final_y})")
        
        # Fallback or default positioning
        if not replace_area_enabled or len(replace_coords) != 4: 
            logging.debug("[Watermark] Using general positioning mode.")
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except AttributeError:
                 try:
                      text_width, text_height = draw.textsize(text, font=font)
                 except AttributeError:
                      logging.error("[Watermark] Cannot determine text size. Cannot apply watermark.")
                      return False
                      
            margin = 5 # Small margin from edges
            if general_position == 'bottom_center':
                final_x = (img_width - text_width) // 2
                final_y = img_height - text_height - margin
            elif general_position == 'bottom_left':
                final_x = margin
                final_y = img_height - text_height - margin
            elif general_position == 'bottom_right':
                final_x = img_width - text_width - margin
                final_y = img_height - text_height - margin
            elif general_position == 'top_center':
                final_x = (img_width - text_width) // 2
                final_y = margin
            else: 
                logging.warning(f"[Watermark] Unknown general position '{general_position}'. Defaulting to bottom_center.")
                final_x = (img_width - text_width) // 2
                final_y = img_height - text_height - margin
            
            final_color = general_color # Use general text color

        # --- Draw the Text --- 
        logging.debug(f"[Watermark] Drawing text '{text}' at ({final_x}, {final_y}) with color {final_color}")
        draw.text((final_x, final_y), text, font=font, fill=final_color)

        # --- Save --- 
        img.save(image_path, "PNG")
        if replace_area_enabled and len(replace_coords) == 4:
             logging.info(f"[Watermark] Applied custom watermark inside replaced area to: {os.path.basename(image_path)}")
        else:
             logging.info(f"[Watermark] Applied custom watermark using general position to: {os.path.basename(image_path)}")
        return True

    except Exception as e:
        logging.error(f"[Watermark] Failed to apply watermark to {image_path}: {e}")
        logging.error(traceback.format_exc())
        return False

# --- End Custom Watermark Function ---
