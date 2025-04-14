import requests, random, os, logging
import numpy as np  # Make sure we have numpy for image processing
from functools import wraps
import time
import re
from typing import Dict, Any, Optional

# Silence TensorFlow output
import sys, warnings
# original_stderr = sys.stderr # Removed stderr redirection
# sys.stderr = open(os.devnull, 'w') # Removed stderr redirection
warnings.filterwarnings('ignore')

# Import TensorFlow silently
import tensorflow as tf
logging.getLogger('tensorflow').setLevel(logging.ERROR) # Use standard logging

# Import NSFW detection functions
# Removed: import opennsfw2 as n2 
from opennsfw2 import predict_image, make_open_nsfw_model

# Restore stderr
# sys.stderr = original_stderr # Removed stderr redirection

from PIL import Image

# Import the specific function needed from src.files
from src.files import apply_custom_watermark

# Initialize the NSFW model globally within this module
# Consider moving this to a central initialization spot if called very frequently
nsfw_model = None # Initialize as None
try:
    logging.info("Initializing NSFW model...") # Add log
    nsfw_model = make_open_nsfw_model()
    logging.info("NSFW model initialized successfully.") # Add log
except Exception as e:
     logging.error(f"Failed to initialize NSFW model in download module: {e}")
     # nsfw_model remains None, checks below will handle this

class DownloadError(Exception):
    """Custom exception for download related errors"""
    pass

def retry_with_backoff(retries=3, backoff_in_seconds=1):
    """
    Retry decorator with exponential backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except requests.RequestException as e:
                    if x == retries:
                        raise DownloadError(f"Failed after {retries} retries: {str(e)}")
                    wait = (backoff_in_seconds * 2 ** x + 
                           random.uniform(0, 1))
                    time.sleep(wait)
                    x += 1
        return wrapper
    return decorator

@retry_with_backoff(retries=3)
def get_asset_id(cookie, clothing_id, debug_mode=False, timeout=10):
    try:
        response = requests.get(
            f'https://assetdelivery.roblox.com/v1/assetId/{clothing_id}',
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("IsCopyrightProtected"):
            logging.warning(f"Copyright Protected! ID: {clothing_id}")
            return None
            
        location = data.get('location')
        if not location:
            if debug_mode:
                logging.debug(f"No location found for clothing ID: {clothing_id}")
            return None
            
        asset_id_response = requests.get(location, timeout=timeout)
        asset_id_response.raise_for_status()
        asset_id_content = str(asset_id_response.content)
        
        try:
            asset_id = asset_id_content.split('<url>http://www.roblox.com/asset/?id=')[1].split('</url>')[0]
        except IndexError:
            logging.error(f"Failed to parse asset ID from response: {asset_id_content}")
            return None
            
        if debug_mode:
            logging.debug(f"Retrieved asset ID: {asset_id} for clothing ID: {clothing_id}")
        return asset_id
        
    except requests.Timeout:
        logging.error(f"Timeout getting asset ID for clothing ID: {clothing_id}")
        raise
    except requests.RequestException as e:
        logging.error(f"Error getting asset ID: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error getting asset ID: {e}")
        return None

@retry_with_backoff(retries=3)
def get_png_url(cookie, asset_id, debug_mode=False, timeout=10):
    try:
        response = requests.get(
            f'https://assetdelivery.roblox.com/v1/assetId/{asset_id}',
            cookies={".ROBLOSECURITY": cookie.cookie},
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("IsCopyrightProtected"):
            logging.warning(f"Copyright Protected! ID: {asset_id}")
            return None
            
        png_url = data.get('location')
        if not png_url:
            logging.warning(f"No PNG URL found for asset ID: {asset_id}")
            return None
            
        if debug_mode:
            logging.debug(f"PNG URL for asset {asset_id}: {png_url}")
            
        png_response = requests.get(png_url, timeout=timeout)
        png_response.raise_for_status()
        return png_response.content
        
    except requests.Timeout:
        logging.error(f"Timeout getting PNG URL for asset ID: {asset_id}")
        raise
    except requests.RequestException as e:
        logging.error(f"Error getting PNG URL: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error getting PNG URL: {e}")
        return None

def replace_template(path, target_dir=None):
    img1 = Image.open(path)
    img2 = Image.open("src/assets/template/template.png")
    img1.paste(img2, (0,0), mask = img2)
    
    if target_dir:
        # Construct filename and ensure target directory exists
        filename = os.path.basename(path)
        final_path = os.path.join(target_dir, filename)
        # The target_dir itself should be created *before* calling save_asset
        # os.makedirs(target_dir, exist_ok=True)
    else:
        # Default behavior: save to src/assets/shirts or src/assets/pants
        final_path = path.replace("temp", "")
        # Ensure the default target directory exists
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        
    img1.save(final_path)
    os.remove(path) # Remove the temporary file
    return final_path # Return the actual final path

def save_asset(cookie, clothing_id, asset_type, asset_name, max_score, path_2, config: Dict, debug_mode=False, target_dir=None):
 try:
    # --- START Sanitization ---
    # Use regex to replace invalid filename characters with underscores
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', asset_name)
    # Remove potentially problematic leading/trailing whitespace/dots
    sanitized_name = sanitized_name.strip('. ')
    if not sanitized_name:
        sanitized_name = f"asset_{clothing_id}" # Fallback name
    # You might want to add length limiting too if needed, similar to save_original_asset
    # --- END Sanitization ---
    
    # Create the temporary directory structure first
    temp_save_dir = os.path.join(path_2, "src", "assets", "temp", asset_type)
    os.makedirs(temp_save_dir, exist_ok=True)
    
    # Use the SANITIZED name for the unique temp filename
    temp_filename = f"{sanitized_name}_{clothing_id}_{random.randint(0, 10000)}.png"
    path = os.path.join(temp_save_dir, temp_filename) 
    
    # Download thumbnail to temp file (used only for NSFW check)
    thumb_data = get_thumbnail(clothing_id)
    if not thumb_data:
        logging.warning(f"Could not get thumbnail for NSFW check: {clothing_id}")
        return False # Cannot perform NSFW check
        
    with open(path, "wb") as f:
        f.write(thumb_data)
    
    # Check NSFW content (only if model loaded)
    nsfw_score = 0.0 # Default to SFW if model failed
    if nsfw_model:
        try:
             # Correctly call predict_image and get NSFW score
             nsfw_score = predict_image(path)
        except Exception as nsfw_e:
             logging.error(f"Error during NSFW prediction for {path}: {nsfw_e}. Skipping check.")
             nsfw_score = 0.0 # Treat as SFW on prediction error
    else:
         logging.warning("NSFW model not available. Skipping NSFW check.")

    if debug_mode:
        logging.debug(f"NSFW score for {asset_name}: {nsfw_score:.4f} (max allowed: {max_score})")
    
    # Remove thumbnail temp file after check
    try: os.remove(path)
    except OSError as e: logging.warning(f"Could not remove temp thumbnail {path}: {e}")
        
    if nsfw_score > max_score:
        logging.warning(f"Asset failed to pass nudity check: {clothing_id}, Score: {nsfw_score:.4f}")
        return False
    
    # Get asset ID and PNG
    asset_id = get_asset_id(cookie, clothing_id, debug_mode)
    if not asset_id:
        logging.warning("Failed to scrape asset item id")
        return False
    
    png = get_png_url(cookie, asset_id, debug_mode)
    if not png:
        logging.warning("Failed to download asset png")
        return False
    
    # Save final PNG data to a *new* temporary file path for processing
    path = os.path.join(temp_save_dir, temp_filename)
    with open(path, 'wb') as f:
        f.write(png)
        
    # Process template and move to final destination (default or target_dir)
    final_saved_path = replace_template(path, target_dir=target_dir) 
    
    if final_saved_path: # Check if replace_template succeeded
        logging.info(f"Downloaded one asset to: {final_saved_path}")
        
        # --- APPLY WATERMARK --- 
        if "custom_watermark" in config:
             watermark_success = apply_custom_watermark(final_saved_path, config["custom_watermark"])
             if not watermark_success:
                 logging.warning(f"Failed to apply watermark to {os.path.basename(final_saved_path)}")
                 # Decide if this should be a failure (return False) or just a warning.
                 # For now, log warning and continue.
        else:
             logging.warning("'custom_watermark' configuration missing. Skipping watermark application.")
        # --------------------- 
             
        return final_saved_path # Return path even if watermarking had issues (logged above)
    else:
        logging.error(f"Failed during template replacement for {path}")
        return False
        
 except Exception as e:
    logging.error(f"ERROR saving asset: {e}")
    # Try to remove the temp file if it exists
    try:
        if 'path' in locals() and os.path.exists(path):
             os.remove(path)
    except Exception as cleanup_e:
        logging.warning(f"Failed to cleanup temp file {path if 'path' in locals() else 'N/A'}: {cleanup_e}")
    return False

@retry_with_backoff(retries=3)
def get_thumbnail(asset_id, timeout=10):
    try:
        response = requests.post(
            "https://thumbnails.roblox.com/v1/batch",
            json=[{
                "format": "png",
                "requestId": f"{asset_id}::Asset:420x420:png:regular",
                "size": "420x420",
                "targetId": asset_id,
                "token": "",
                "type": "Asset"
            }],
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get("data"):
            logging.error(f"No thumbnail data returned for asset ID: {asset_id}")
            return None
            
        image_url = data["data"][0].get("imageUrl")
        if not image_url:
            logging.error(f"No image URL in thumbnail data for asset ID: {asset_id}")
            return None
            
        img_response = requests.get(image_url, timeout=timeout)
        img_response.raise_for_status()
        return img_response.content
        
    except requests.Timeout:
        logging.error(f"Timeout getting thumbnail for asset ID: {asset_id}")
        raise
    except requests.RequestException as e:
        logging.error(f"Error getting thumbnail: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error getting thumbnail: {e}")
        return None

def save_original_asset(cookie, clothing_id, identifier, asset_type, asset_name, path_base, config: Dict, save_folder_type='group', debug_mode=False):
    """
    Downloads and saves the original clothing asset PNG without modification.
    
    Args:
        cookie: The Roblox cookie object.
        clothing_id: The catalog ID of the clothing item.
        identifier: The group ID (if save_folder_type='group') or potentially a keyword/session ID.
        asset_type: 'classicshirts' or 'classicpants'.
        asset_name: Original name of the asset for filename.
        path_base: Base directory (e.g., os.getcwd()).
        save_folder_type (str): Either 'group' or 'keyword' to determine subdirectory.
        debug_mode: Whether to print debug info.

    Returns:
        The final path to the saved original PNG, or False on failure.
    """
    temp_path = None # Define temp_path outside try block
    final_path = None # Define final_path as well
    try:
        # 1. Get the actual template asset ID
        asset_id = get_asset_id(cookie, clothing_id, debug_mode)
        if not asset_id:
            # Logging handled within get_asset_id
            return False

        # 2. Get the original PNG data using the template asset ID
        png_data = get_png_url(cookie, asset_id, debug_mode)
        if not png_data:
            # Logging handled within get_png_url
            return False

        # 3. Sanitize asset name for filename 
        # Use regex to replace invalid filename characters with underscores
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', asset_name)
        # Remove potentially problematic leading/trailing whitespace/dots
        sanitized_name = sanitized_name.strip('. ')
        if not sanitized_name:
            sanitized_name = f"asset_{clothing_id}" # Fallback name
            
        # Limit filename length (example: 100 chars + extension)
        max_len = 100
        if len(sanitized_name) > max_len:
             sanitized_name = sanitized_name[:max_len]
             logging.debug(f"Truncated filename to: {sanitized_name}")
             
        filename = f"{sanitized_name}_{clothing_id}.png"

        # 4. Determine save directory based on type
        if save_folder_type == 'group':
             target_save_dir = os.path.join(path_base, "src", "assets", "original_group_downloads", str(identifier), asset_type) 
        elif save_folder_type == 'keyword':
             target_save_dir = os.path.join(path_base, "src", "assets", "original_keyword_downloads", str(identifier), asset_type)
        else:
            logging.error(f"Invalid save_folder_type: {save_folder_type}")
            return False
            
        os.makedirs(target_save_dir, exist_ok=True)

        # 5. Construct final path and save
        final_path = os.path.join(target_save_dir, filename)
        
        # Check for existing file to avoid overwrite or use temp file strategy
        if os.path.exists(final_path):
            logging.warning(f"Original asset already exists: {final_path}. Skipping save.")
            # Decide: return existing path, return False, or overwrite?
            # For now, returning existing path if it's already there.
            return final_path 
            
        with open(final_path, 'wb') as f:
            f.write(png_data)
            
        logging.info(f"Saved original asset to: {final_path}")
        
        # --- APPLY WATERMARK TO ORIGINAL --- 
        if "custom_watermark" in config:
             watermark_success = apply_custom_watermark(final_path, config["custom_watermark"])
             if not watermark_success:
                 logging.warning(f"Failed to apply watermark to original asset {os.path.basename(final_path)}")
                 # Log warning and continue.
        else:
            logging.warning("'custom_watermark' configuration missing. Skipping watermark application for original asset.")
        # --------------------------------- 
            
        return final_path

    except Exception as e:
        logging.error(f"Error saving original asset {clothing_id}: {e}")
        # Clean up final file if it exists and save failed midway?
        # if final_path and os.path.exists(final_path): 
        #    try: os.remove(final_path) 
        #    except: pass
        return False
