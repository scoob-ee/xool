import requests, random, re, json, time, logging

def scrape_assets(cookie, keywords, subcategory, advanced_params=None, debug_mode=False):
    """
    Scrape assets from Roblox catalog with enhanced parameter support.
    
    Args:
        cookie: The Roblox cookie object
        keywords: Search keywords string
        subcategory: 'classicshirts' or 'classicpants'
        advanced_params: Optional dict of additional parameters to customize the search
        debug_mode: Whether to print debug info
    
    Returns:
        List of asset IDs
    """
    # Default parameters
    params = {
        "category": "Clothing",
        "limit": 120,
        "salesTypeFilter": 1,
        "sortAggregation": random.choice(['1', '3', '5']),
        "sortType": random.randint(0, 2),
        "subcategory": subcategory,
        "minPrice": 5,
        "keyword": keywords
    }
    
    # Override with advanced params if provided
    if advanced_params:
        params.update(advanced_params)
    
    # Build URL with query parameters
    url = "https://catalog.roblox.com/v1/search/items"
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    
    # Debug info
    if debug_mode:
        logging.debug(f"Search URL: {url}?{query_string}")
        
    # Make request
    items = requests.get(f"{url}?{query_string}", 
                        cookies={".ROBLOSECURITY": cookie.cookie}, 
                        headers={"x-csrf-token": cookie.x_token()})
    if items.status_code == 200:
        result = [item['id'] for item in items.json()["data"]]
        if debug_mode:
            logging.debug(f"Found {len(result)} items with keyword: {keywords}")
        return result
    else:
        logging.error(f"Search failed with status code {items.status_code}: {items.text}")
        return []

def sort_assets(cookie, ids, blacklisted_creators, blacklisted_words, upload_without_blacklisted_words):
    response = requests.post("https://catalog.roblox.com/v1/catalog/items/details", 
                            json={"items": [{"itemType": "Asset", "id": id} for id in ids]},
                            cookies={".ROBLOSECURITY": cookie.cookie},
                            headers={"x-csrf-token": cookie.x_token()})
    if response.status_code == 200:
     items = []
     for item in response.json()["data"]:
        dnd = False
        if item["creatorTargetId"] in blacklisted_creators:
            continue
        item["name"] = re.sub(r'[<>:"/\\|?*]', '_', item['name'])
        for blacklisted_word in blacklisted_words:
            if blacklisted_word in item["name"]:
                if upload_without_blacklisted_words:
                    item["name"].replace(blacklisted_word, "")
                    items.append(item)
                else:
                    dnd = True
                    break
        if dnd:
            continue
        else:
            item["name"] = item['name'].replace("/", " ")
            items.append(item)
     return items
    elif response.status_code == 403:
        raise Exception("403")
    elif response.status_code == 429:
        raise Exception("Ratelimit hit. This may take a while to go away.")
    else:
        return []

def get_optimal_sort_params(target="popular"):
    """
    Return optimal sort parameters based on target strategy.
    
    Args:
        target: One of "popular", "newest", "relevant", or "random"
    
    Returns:
        Dict with sortAggregation and sortType parameters
    """
    if target == "popular":
        return {"sortAggregation": "5", "sortType": "2"}  # Most favorited/purchased
    elif target == "newest":
        return {"sortAggregation": "3", "sortType": "0"}  # Newest items
    elif target == "relevant":
        return {"sortAggregation": "1", "sortType": "0"}  # Most relevant
    elif target == "random":
        return {
            "sortAggregation": random.choice(['1', '3', '5']),
            "sortType": str(random.randint(0, 2))
        }
    else:
        return {}  # Default to random behavior

def generate_keyword_combinations(config, max_combinations=5, debug_mode=False):
    """
    Generate dynamic keyword combinations from config categories.
    
    Args:
        config: Application configuration dictionary with keyword categories
        max_combinations: Maximum number of keyword combinations to generate
        debug_mode: Whether to print debug info
    
    Returns:
        List of keyword combinations as strings
    """
    combinations = []
    
    # Get categories from config
    categories = config.get("keyword_categories", {})
    styles = categories.get("styles", [])
    colors = categories.get("colors", [])
    types = categories.get("types", [])
    details = categories.get("details", [])
    
    if debug_mode:
        logging.debug(f"Keyword categories loaded - styles: {len(styles)}, colors: {len(colors)}, " +
                     f"types: {len(types)}, details: {len(details)}")
    
    # If no categories are defined, return the default search tag
    if not any([styles, colors, types, details]):
        default_tag = config.get("searching_tags", "")
        if debug_mode:
            logging.debug(f"No keyword categories defined, using default tag: {default_tag}")
        return [default_tag]
    
    # Generate combinations
    for _ in range(max_combinations):
        parts = []
        
        # Simple pattern selection (1-3 for variety)
        pattern = random.randint(1, 3)
        
        if pattern == 1:
            # Pattern 1: Style + Type + Color
            # Example: "y2k cargo pants black"
            if styles and random.random() > 0.3:  # 70% chance
                parts.append(random.choice(styles))
                
            if types:  # Always include a type
                parts.append(random.choice(types))
                
            if colors and random.random() > 0.3:  # 70% chance
                parts.append(random.choice(colors))
        
        elif pattern == 2:
            # Pattern 2: Style + Color + Type + Detail
            # Example: "vintage olive ripped jeans distressed"
            if styles and random.random() > 0.4:  # 60% chance
                parts.append(random.choice(styles))
                
            if colors and random.random() > 0.4:  # 60% chance
                parts.append(random.choice(colors))
                
            if types:  # Always include a type
                parts.append(random.choice(types))
                
            if details and random.random() > 0.5:  # 50% chance
                parts.append(random.choice(details))
        
        else:
            # Pattern 3: Detail + Type + Color
            # Example: "oversized hoodie black"
            if details and random.random() > 0.4:  # 60% chance
                parts.append(random.choice(details))
                
            if types:  # Always include a type
                parts.append(random.choice(types))
                
            if colors and random.random() > 0.4:  # 60% chance
                parts.append(random.choice(colors))
                
            if styles and random.random() > 0.6:  # 40% chance
                parts.append(random.choice(styles))
        
        # Make sure we have at least 2-3 parts for an effective search
        if len(parts) < 2:
            # Need to add more terms for effective search
            if types and not any(type_word in parts for type_word in types):
                parts.append(random.choice(types))
                
            if styles and not any(style in parts for style in styles) and random.random() > 0.5:
                parts.append(random.choice(styles))
        
        # Randomize the order of keywords for more variety
        random.shuffle(parts)
        
        if parts:  # Only append if we have something
            combinations.append(" ".join(parts))
    
    # Make sure we return at least one combination
    if not combinations:
        default_tag = config.get("searching_tags", "")
        if debug_mode:
            logging.debug(f"No combinations generated, using default tag: {default_tag}")
        return [default_tag]
    
    # Remove any duplicate combinations
    combinations = list(dict.fromkeys(combinations))
    
    # If we lost combinations due to deduplication, generate some more
    while len(combinations) < max_combinations and len(combinations) < 20:  # Cap at 20 attempts
        # Create simple, effective combinations
        style = random.choice(styles) if styles and random.random() > 0.4 else ""
        color = random.choice(colors) if colors and random.random() > 0.4 else ""
        type_word = random.choice(types) if types else ""
        detail = random.choice(details) if details and random.random() > 0.6 else ""
        
        # Always include at least a type word
        parts = [p for p in [style, color, type_word, detail] if p]
        if not parts or not any(t in parts for t in types):
            continue
            
        # Shuffle for variety
        random.shuffle(parts)
        combo = " ".join(parts)
        
        if combo and combo not in combinations:
            combinations.append(combo)
    
    # Log the generated combinations
    if debug_mode:
        logging.debug(f"Generated keyword combinations: {combinations}")
    else:
        logging.info(f"Generated {len(combinations)} keyword combinations")
    
    return combinations[:max_combinations]  # Ensure we return at most max_combinations

def search_with_multiple_keywords(cookie, config, subcategory, advanced_params=None, debug_mode=False):
    """
    Perform searches with multiple keyword combinations and aggregates results.
    
    Args:
        cookie: The Roblox cookie object
        config: Application configuration dictionary
        subcategory: 'classicshirts' or 'classicpants'
        advanced_params: Optional dict of additional parameters to customize the search
        debug_mode: Whether to print debug info
        
    Returns:
        List of unique asset IDs from all searches
    """
    # Get the maximum number of combinations to use
    max_combinations = config.get("keyword_strategy", {}).get("max_combinations", 3)
    
    # Generate keyword combinations
    keyword_combinations = generate_keyword_combinations(config, max_combinations, debug_mode)
    
    # If using traditional search, just use the single keyword string
    if not config.get("keyword_strategy", {}).get("enable_dynamic_keywords", True):
        keyword_combinations = [config.get("searching_tags", "")]
        if debug_mode:
            logging.debug("Dynamic keywords disabled, using single keyword string")
    
    # Search with each keyword combination
    all_results = []
    for keywords in keyword_combinations:
        if not keywords.strip():  # Skip empty keyword strings
            if debug_mode:
                logging.debug("Skipping empty keyword string")
            continue
            
        logging.info(f"Searching with keywords: {keywords}")
        results = scrape_assets(cookie, keywords, subcategory, advanced_params, debug_mode)
        all_results.extend(results)
        
        # Sleep briefly between searches to avoid rate limiting
        time.sleep(0.5)
    
    # Remove duplicates while preserving order
    unique_results = []
    seen = set()
    for item_id in all_results:
        if item_id not in seen:
            seen.add(item_id)
            unique_results.append(item_id)
    
    logging.info(f"Found {len(unique_results)} unique items across {len(keyword_combinations)} keyword combinations")
    return unique_results

def scrape_group_assets(cookie, group_id, subcategory, debug_mode=False, limit_per_page=120, max_retries=3, sleep_between_pages=1):
    """
    Scrape all clothing assets created by a specific group ID using pagination.

    Args:
        cookie: The Roblox cookie object.
        group_id: The target Roblox Group ID.
        subcategory: 'classicshirts' or 'classicpants'.
        debug_mode: Whether to print debug info.
        limit_per_page: Number of items to fetch per API call.
        max_retries: Maximum number of retries for failed requests.
        sleep_between_pages: Seconds to wait between fetching pages.

    Returns:
        List of asset IDs created by the group.
    """
    all_asset_ids = []
    cursor = ""
    page_num = 1
    retries = 0

    while True:
        params = {
            "category": "Clothing",
            "subcategory": subcategory,
            "limit": limit_per_page,
            "creatorType": "Group",
            "creatorTargetId": group_id,
            "cursor": cursor,
            # Add other potentially useful defaults if needed, e.g., sortType=0?
        }
        
        url = "https://catalog.roblox.com/v1/search/items"
        query_string = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])

        if debug_mode:
            logging.debug(f"Scraping Group {group_id} - {subcategory} - Page {page_num} - Cursor: {cursor}")
            logging.debug(f"Request URL: {url}?{query_string}")

        try:
            response = requests.get(
                f"{url}?{query_string}",
                cookies={".ROBLOSECURITY": cookie.cookie},
                headers={"x-csrf-token": cookie.x_token()},
                timeout=15  # Increased timeout for potentially larger requests
            )

            if response.status_code == 200:
                retries = 0 # Reset retries on success
                data = response.json()
                current_page_ids = [item['id'] for item in data.get("data", []) if item.get('id')]
                all_asset_ids.extend(current_page_ids)
                
                if debug_mode:
                    logging.debug(f"Page {page_num}: Found {len(current_page_ids)} items.")

                cursor = data.get("nextPageCursor")
                if not cursor:
                    logging.info(f"Finished scraping group {group_id} for {subcategory}. Found {len(all_asset_ids)} total items.")
                    break  # Exit loop if no next page

                page_num += 1
                time.sleep(sleep_between_pages) # Wait before fetching next page

            elif response.status_code == 429:
                retries += 1
                if retries > max_retries:
                    logging.error(f"Rate limit exceeded after {max_retries} retries. Aborting group scrape.")
                    break
                wait_time = (2 ** retries) + random.uniform(0, 1) # Exponential backoff
                logging.warning(f"Rate limited (429). Retrying page {page_num} in {wait_time:.2f} seconds... (Retry {retries}/{max_retries})")
                time.sleep(wait_time)
                # Don't advance cursor or page number, just retry the same request

            elif response.status_code == 403:
                 logging.error("Forbidden (403) scraping group assets. Check cookie validity and permissions.")
                 # Maybe try refreshing token once?
                 cookie.generate_token() 
                 retries += 1
                 if retries > max_retries:
                    logging.error(f"403 persists after {max_retries} retries. Aborting group scrape.")
                    break
                 time.sleep(2) # Short sleep before retry after token refresh
                 
            else:
                retries += 1
                logging.error(f"Error scraping group {group_id} (Page {page_num}): Status {response.status_code} - {response.text}")
                if retries > max_retries:
                     logging.error(f"Failed to fetch page {page_num} after {max_retries} retries. Aborting group scrape.")
                     break
                wait_time = (2 ** retries) # Exponential backoff
                logging.warning(f"Retrying page {page_num} in {wait_time:.2f} seconds... (Retry {retries}/{max_retries})")
                time.sleep(wait_time)

        except requests.Timeout:
             retries += 1
             logging.error(f"Timeout scraping group {group_id} (Page {page_num}).")
             if retries > max_retries:
                 logging.error(f"Timeout persists after {max_retries} retries. Aborting group scrape.")
                 break
             wait_time = (2 ** retries)
             logging.warning(f"Retrying page {page_num} in {wait_time:.2f} seconds... (Retry {retries}/{max_retries})")
             time.sleep(wait_time)
             
        except Exception as e:
            logging.error(f"Unexpected error scraping group {group_id} (Page {page_num}): {e}")
            # Don't retry on unexpected errors immediately, break to avoid loops
            break

    return all_asset_ids
