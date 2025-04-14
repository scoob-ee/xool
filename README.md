# Xool - Roblox Clothing Automation Tool

Xool is a tool for automatically scraping, filtering, and uploading clothing items to Roblox.

## Features

*   Automated clothing scraping from Roblox catalog based on keywords.
*   Configurable search strategies (popular, newest, relevant, random).
*   Advanced duplicate image detection using multiple hashing algorithms.
*   NSFW content filtering.
*   Blacklisting creators or specific keywords.
*   Automatic uploading to specified Roblox groups.
*   Optional custom watermarking.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url> # Replace <repository-url> with the actual URL
    cd xool-main # Or your project directory name
    ```

2.  **Set up a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Copy/Rename `config.example.json` to `config.json`** (if an example file exists, otherwise create `config.json` manually).

2.  **Edit `config.json`:**
    *   **`groups`**: Add your Roblox Group ID(s).
    *   **`uploader_cookies`**: VERY IMPORTANT - Add the `.ROBLOSECURITY` cookie for an account that has permission to upload to the specified group(s). Find this in your browser's developer tools (Application > Cookies).
        *   **Security Warning:** Never share your `.ROBLOSECURITY` cookie. Treat it like a password.
    *   **`assets_price`**: Set the price for uploaded items.
    *   **`max_nudity_value`**: Adjust NSFW filter sensitivity (0.0 to 1.0, lower is stricter).
    *   Review and adjust other settings like `search_keywords`, `search_strategy`, `duplicate_detection`, and `custom_watermark` as needed.

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
   - **min_price** / **max_price**: Price range filters.
   - **limit**: Maximum number of results to fetch per keyword search.

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

## Requirements

See `requirements.txt` for the full list of Python dependencies. 