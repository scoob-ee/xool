# Xool - Roblox Clothing Automation Tool

Xool is a tool for automatically scraping, filtering, and uploading clothing items to Roblox.

## Features

*   Automated clothing scraping from Roblox catalog based on keywords.
*   Configurable search strategies (popular, newest, relevant, random).
*   Advanced duplicate image detection using multiple hashing algorithms.
*   NSFW content filtering.
*   Blacklisting creators or specific keywords.
*   Automatic uploading to specified Roblox groups.*   
*   Custom watermarking.

## Requirements

*   **Python 3.7.9**: This specific version is required. See installation instructions below for setting up a virtual environment with this version.
*   Dependencies listed in `requirements.txt`.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url> # Replace <repository-url> with the actual URL
    cd xool-main # Or your project directory name
    ```

2.  **Set up a Python 3.7.9 Virtual Environment (Recommended):**
    
    Using the correct Python version is crucial. A virtual environment keeps dependencies isolated.

    *   **Method 1: Using `pyenv` (Recommended for managing multiple Python versions):**
        *   Install `pyenv` and `pyenv-virtualenv` (follow their official installation guides for your OS).
        *   Install Python 3.7.9: `pyenv install 3.7.9`
        *   Create a virtual environment: `pyenv virtualenv 3.7.9 xool-venv-3.7.9`
        *   Activate the environment: `pyenv activate xool-venv-3.7.9` (or use `pyenv local xool-venv-3.7.9` to activate automatically when in the directory).

    *   **Method 2: Using Python's built-in `venv` (If you have Python 3.7.9 installed system-wide or available):**
        *   Ensure you are using your Python 3.7.9 executable.
        *   Create the environment: `python3.7 -m venv venv` (or `python -m venv venv` if `python` points to 3.7.9)
        *   Activate:
            *   Windows: `.\venv\Scripts\activate`
            *   macOS/Linux: `source venv/bin/activate`

3.  **Install dependencies (inside the activated virtual environment):**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Configuration is handled through the `config.json` file.

**Steps:**

1.  **Locate `config.json`**: This file should be in the root directory of the project.

2.  **Edit `config.json`**: Open the file in a text editor.
    *   **`groups`**: This is a dictionary where each key is a Roblox Group ID (as a string) that you want the bot to interact with.
    *   **`uploader_cookies`**: **VERY IMPORTANT** - Inside *each* group ID object within `groups`, you **must** add/edit the `uploader_cookies` key. This should be a list containing **one** string: your `.ROBLOSECURITY` cookie for an account that has permission to upload to that specific group.
        *   Find this cookie in your browser's developer tools (usually under Application -> Cookies for the Roblox domain).
        *   **Example Structure:**
          ```json
          {
              "groups": {
                  "1234567": { 
                      "uploader_cookies": ["_|WARNING:-DO-NOT-SHARE-THIS...YourCookieValueHere...|_"],
                      "_comment": "Optional: Add comments for this group"
                  },
                  "9876543": {
                      "uploader_cookies": ["_|WARNING:-DO-NOT-SHARE-THIS...AnotherCookieValue...|_"]
                  }
              },
              // ... other settings ...
          }
          ```
        *   Replace the placeholder cookie with your actual cookie value.
    *   **Other Settings**: Review and adjust other settings like `assets_price`, `search_strategy`, `duplicate_detection`, `custom_watermark`, etc., to your preferences.

## Usage

1.  Ensure you have completed the Installation and Configuration steps.
2.  Make sure your virtual environment is activated (if you created one).
3.  Run the main script:
    ```bash
    python main.py
    ```
4.  The tool will start searching, downloading, filtering, and uploading assets based on your configuration.

## Detailed Feature Configuration

### Search Configuration

The tool searches for clothing items using a list of keywords you provide and allows fine-tuning of the search results.

#### How It Works

The search system:

1. Uses a list of keywords defined in the `search_keywords` section of your `config.json`.
2. Randomly picks one keyword from your list for each search cycle.
3. Applies search result sorting/filtering based on the `search_strategy` settings:
   - **mode**: `popular` (most favorited/purchased), `newest` (most recent), `relevant` (most relevant to the keyword), `random`.


#### Configuration

You configure the keywords and search strategy in your `config.json` file:

```json
"search_keywords": [
    "aesthetic shirt",
    "y2k pants",
    "goth outfit",
    "vintage hoodie"
 ],
"search_strategy": {
    "mode": "popular",       // Options: "popular", "newest", "relevant", "random"
    "min_price": 5,          // Minimum price to search for
    "max_price": 100,        // Maximum price (0 for no limit)
    "limit": 120             // Maximum number of results to fetch per keyword
}
```

#### Choosing the Right Search Mode

The `mode` setting in `search_strategy` influences how Roblox sorts the results for your chosen keyword:

- **Popular**: Best for finding proven sellers for that keyword.
- **Newest**: Best for finding fresh designs related to that keyword.
- **Relevant**: Best when you want Roblox's default relevance ranking for the keyword.
- **Random**: Uses random sorting parameters, good for general exploration.

### Advanced Duplicate Detection

The tool also includes an advanced duplicate detection system that combines multiple image hashing algorithms to more effectively detect similar clothing items. This prevents uploading duplicates even if they have different filenames or minor visual differences.

#### How It Works

The advanced duplicate detection system:

1. Uses 5 different perceptual hash algorithms:
   - Perceptual Hash (pHash) - Good at detecting structural similarities
   - Difference Hash (dHash) - Good at detecting gradient changes
   - Average Hash (aHash) - Simple but effective for many cases
   - Wavelet Hash (wHash) - Good at detecting significant visual features
   - Color Hash - Detects similarities in color distribution

2. Compares new images to all existing images in your assets folder

3. Considers an image a duplicate if at least `min_algorithm_matches` (configurable) algorithms detect similarity based on their respective `thresholds`.

4. Provides detailed information about which existing file matched the new one.

#### Configuration

You can fine-tune the duplicate detection in your `config.json` file:

```json
"duplicate_detection": {
    "use_advanced": true,           // Enable advanced detection (true) or use legacy method (false)
    "min_algorithm_matches": 2,     // How many algorithms must detect similarity (1-5)
    "thresholds": {                 // Lower values = stricter matching (more sensitive)
        "phash": 3,                 // Perceptual hash threshold
        "dhash": 3,                 // Difference hash threshold
        "ahash": 5,                 // Average hash threshold 
        "whash": 3,                 // Wavelet hash threshold
        "colorhash": 4              // Color hash threshold
    }
}
```

#### Adjusting Sensitivity

- For **stricter** duplicate detection (catches more potential duplicates, might have more false positives):
  - Lower the threshold values (e.g., `phash: 2`)
  - Decrease `min_algorithm_matches` (e.g., `1`)

- For **more lenient** duplicate detection (catches only very similar images):
  - Increase the threshold values (e.g., `phash: 5`)
  - Increase `min_algorithm_matches` (e.g., `3` or `4`)

### Duplicate Upload Prevention (Upload Log)

To prevent uploading the exact same asset to the same group multiple times across different sessions, the tool utilizes an upload log.

#### How It Works

1.  **Central Log File:** A single file, `src/assets/upload_logs/upload_log.txt`, keeps a history of all successful uploads.
2.  **Image Hashing:** Before attempting an upload, the script calculates a unique SHA256 hash (a digital fingerprint) of the image file.
3.  **Logging on Success:** When an asset is successfully uploaded and released for sale, a new line is added to `upload_log.txt`. This line contains the Group ID the asset was uploaded to and the calculated image hash, separated by a comma (e.g., `1234567,a1b2c3d4e5f6...`).
4.  **Pre-Upload Check:** Before uploading any new asset, the script checks this log file. If a line already exists matching both the target Group ID and the hash of the image about to be uploaded, the upload is skipped, and a message is logged indicating it's a duplicate based on the upload history.

This ensures that even if you restart the script or process the same source images again, you won't waste time or Robux uploading identical assets to groups where they already exist.

## Requirements

- **Python 3.7.9** (See Installation section)
- Dependencies listed in `requirements.txt`. #   X o o l  
 