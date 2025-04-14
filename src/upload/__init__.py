import requests, json, time, uuid, logging
import os
from requests_toolbelt.multipart.encoder import MultipartEncoder

def create_asset(name, path, asset_type, cookie, group_id, description, _total_tries, wait_time):
    payload = {
        "assetType": asset_type,
        "creationContext": {
            "creator": {
                "groupId": group_id
            },
            "expectedPrice": 10
        },  
        "description": description,
        "displayName": name,
    }
    logging.debug(f"Create Asset Payload: {json.dumps(payload)}")
    
    if not os.path.exists(path):
        logging.error(f"File not found at path: {path}")
        return False
        
    file_name = os.path.basename(path)
    _, file_extension = os.path.splitext(path)
    file_mime_type = 'image/png'
    if file_extension.lower() == '.jpg' or file_extension.lower() == '.jpeg':
        file_mime_type = 'image/jpeg'
    elif file_extension.lower() == '.gif':
        file_mime_type = 'image/gif'
    logging.debug(f"Using filename: {file_name}, MIME type: {file_mime_type}")

    try:
        with open(path, 'rb') as file_content_for_post:
            multipart_data = MultipartEncoder(
                fields={
                    'request': json.dumps(payload),
                    'fileContent': (file_name, file_content_for_post, file_mime_type) 
                }
            )
            
            csrf_token = cookie.x_token()
            if not csrf_token:
                logging.error("Failed to get CSRF token.")
                return False
                
            headers = {
                'X-CSRF-TOKEN': csrf_token,
                'Content-Type': multipart_data.content_type,
            }
            log_headers = {k: v for k, v in headers.items() if k.lower() != 'cookie'}
            logging.debug(f"Initial Multipart POST Headers: {log_headers}")
            
            cookies_dict = {".ROBLOSECURITY": cookie.cookie}

            response = requests.post(
                "https://apis.roblox.com/assets/user-auth/v1/assets", 
                data=multipart_data, 
                headers=headers, 
                cookies=cookies_dict,
                timeout=60
            )
            logging.info(f"Initial Multipart POST Response Status Code: {response.status_code}")

            response_json = None
            try:
                response_json = response.json()
                logging.info(f"Initial Multipart POST Response Body: {json.dumps(response_json)}")
            except json.JSONDecodeError:
                logging.error(f"Failed to decode JSON response from initial POST. Status: {response.status_code}, Text: {response.text}")

            if not response.ok:
                logging.error(f"Initial POST request failed with status {response.status_code}.")
                if response_json and response_json.get("message"):
                    message = response_json["message"]
                    print(f"Error Message from Roblox (POST): {message}")
                    if "InsufficientFunds" in message:
                        return 2
                    elif "unauthorized" in message or "permission" in message.lower():
                        return 3
                    elif "moderated" in message:
                         logging.error("Asset name/description failed moderation.")
                         return False 
                else:
                    logging.error(f"POST failed, response text: {response.text}")
                return False

            operation_id = response_json.get("operationId")
            if not operation_id:
                logging.error(f"Initial POST response successful ({response.status_code}) but missing operationId. Response: {response_json}")
                if response_json.get("message"):
                    print(f"Message from Roblox (POST, {response.status_code} OK): {response_json['message']}")
                return False 

    except IOError as io_err:
        logging.error(f"Failed to read file for POST upload: {path}. Error: {io_err}")
        return False
    except requests.RequestException as req_e:
        logging.error(f"HTTP Request failed during initial POST: {req_e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error during initial POST setup/request: {e}")
        return False

    logging.info(f"POST successful. OperationId: {operation_id}. Starting polling...")
    total_tries = 0
    polling_url = f"https://apis.roblox.com/assets/user-auth/v1/operations/{operation_id}"
    polling_headers = {'X-CSRF-TOKEN': csrf_token}
    
    while total_tries < _total_tries:
        try:
            poll_response = requests.get(polling_url, headers=polling_headers, cookies=cookies_dict, timeout=15)
            logging.debug(f"Polling Status: {poll_response.status_code}")
            
            if not poll_response.ok:
                logging.warning(f"Polling request failed with status {poll_response.status_code}. Text: {poll_response.text}")
                total_tries += 1
                time.sleep(wait_time)
                continue

            try:
                poll_json = poll_response.json()
                logging.debug(f"Polling Response: {json.dumps(poll_json)}")
                
                if poll_json.get("done"):
                    logging.info("Polling successful: Operation marked as done.")
                    return poll_json 
                else:
                    pass 
                    
            except json.JSONDecodeError:
                logging.error(f"Failed to decode polling JSON response. Text: {poll_response.text}")

        except requests.RequestException as poll_e:
                logging.error(f"Error during polling request: {poll_e}")
        except Exception as e:
             logging.exception(f"Unexpected error during polling loop: {e}")

        total_tries += 1
        logging.debug(f"Polling attempt {total_tries}/{_total_tries}. Waiting {wait_time}s...")
        time.sleep(wait_time)
            
    logging.error(f"Asset creation polling timed out after {total_tries} tries for operation {operation_id}.")
    return False

def release_asset(cookie, asset_id, price, name, description, group_id):
    headers = {
        "X-CSRF-TOKEN": cookie.x_token(),
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={cookie.cookie};"
    }
    data = {    
        "saleLocationConfiguration": {"saleLocationType": 1, "places": []},
        "targetId": asset_id,
        "priceInRobux": price,
        "publishingType": 2,
        "idempotencyToken": str(uuid.uuid4()),
        "publisherUserId": cookie.user_id,
        "creatorGroupId": group_id,
        "name": name,
        "description": description,
        "isFree": False,
        "agreedPublishingFee": 0,
        "priceOffset": 0,
        "quantity": 0,
        "quantityLimitPerUser": 0,
        "resaleRestriction": 2,
        "targetType": 0
    }
    logging.debug(f"Releasing asset {asset_id} with name '{name}', price {price}")
    try:
        response = requests.post(f"https://itemconfiguration.roblox.com/v1/collectibles", headers=headers, json=data, timeout=30)
        logging.info(f"Release asset response status: {response.status_code}")
        if not response.ok:
             logging.error(f"Release asset failed. Status: {response.status_code}, Text: {response.text}")
             try:
                 logging.error(f"Release asset error JSON: {response.json()}")
             except json.JSONDecodeError:
                 pass
        return response
    except requests.RequestException as e:
        logging.error(f"HTTP error during release_asset: {e}")
        return None 
    except Exception as e:
        logging.exception(f"Unexpected error in release_asset: {e}")
        return None
    
