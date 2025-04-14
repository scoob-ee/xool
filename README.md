# Xool - Roblox Clothing Automation Tool

> This is a inproved fork of [xool](https://github.com/efenatuyo/xool)

Xool is a tool for automatically scraping, filtering, and uploading clothing items to Roblox.

## Features
- Automated clothing scraping from Roblox catalog based on keywords
- Configurable search strategies (popular, newest, relevant, random)
- Advanced duplicate image detection using multiple hashing algorithms
- NSFW content filtering
- Automatic uploading to specified Roblox groups
- Custom watermarking

## Requirements
- **Python 3.7.9**: This specific version is required. See installation instructions below for setting up a virtual environment with this version
- Dependencies listed in `requirements.txt`

## Installation
### 1. Clone the repository
```bash
git clone https://github.com/scoob-ee/xool
cd xool-main
```

### 2. Set up Python 3.7.9 Virtual Environment
> [!IMPORTANT]
> Using the correct Python version is crucial. A virtual environment keeps dependencies isolated.

#### Method 1: Using `pyenv` (Recommended)
This method is best for managing multiple Python versions:

1. Install `pyenv` and `pyenv-virtualenv` (follow their official installation guides for your OS)
2. Install Python 3.7.9:
```bash
pyenv install 3.7.9
```
3. Create a virtual environment:
```bash
pyenv virtualenv 3.7.9 xool-venv-3.7.9
```
4. Activate the environment:
```bash
pyenv activate xool-venv-3.7.9
```
Or use `pyenv local xool-venv-3.7.9` to activate automatically in the directory

#### Method 2: Using Python's built-in `venv`
If you already have Python 3.7.9 installed:

1. Ensure you are using your Python 3.7.9 executable
2. Create the environment:
```bash
# Example using python3.7 command
python3.7 -m venv venv
# Or, if 'python' points to 3.7.9
# python -m venv venv
```
3. Activate the environment:
   - Windows (Command Prompt/PowerShell):
```powershell
.\venv\Scripts\activate
```
   - macOS/Linux (bash/zsh):
```bash
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Configuration
Configuration is handled through the `config.json` file.

### Steps:
1. **Locate `config.json`**: This file should be in the root directory of the project.
2. **Edit `config.json`**: You will need to configure several parts:
   - **`groups`**: This top-level key holds a dictionary. Each key *inside* this dictionary should be a Roblox Group ID (as a string, e.g., `"1234567"`) that you want the bot to interact with.
   - **`uploader_cookies`**: Inside *each* Group ID object (e.g., inside `"1234567": { ... }`), you **must** add/edit the `uploader_cookies` key. The value for this key must be a list containing **one** string: your `.ROBLOSECURITY` cookie. This cookie must belong to an account that has upload permissions for that specific group.

Example Structure:
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
    }
}
```

> [!NOTE]
> Remember to replace the placeholder cookie strings with your actual cookie values.

- **Other Settings**: Review and adjust other general settings like `assets_price`, `search_strategy`, `duplicate_detection`, `custom_watermark`, etc.

## Usage
1. Ensure you have completed the Installation and Configuration steps
2. Make sure your virtual environment is activated (if you created one)
3. Run the main script:
```bash
python main.py
```
4. The tool will start searching, downloading, filtering, and uploading assets based on your configuration

## Detailed Feature Configuration
### Search Configuration
The tool searches for clothing items using a list of keywords you provide and allows fine-tuning of the search results.

#### How It Works
The search system:
1. Uses a list of keywords defined in the `search_keywords` section of your `config.json`
2. Randomly picks one keyword from your list for each search cycle
3. Applies search result sorting/filtering based on the `search_strategy` settings:
   - **mode**: `popular` (most favorited/purchased), `newest` (most recent), `relevant` (most relevant to the keyword), `random`)
   - **min_price** / **max_price**: Price range filters
   - **limit**: Maximum number of results to fetch per keyword search

Configuration Example:
```json
{
    "search_keywords": ["aesthetic shirt", "y2k pants", "goth outfit", "vintage hoodie"],
    "search_strategy": {
        "mode": "popular",
        "min_price": 5,
        "max_price": 100,
        "limit": 120
    }
}
```

#### Search Modes
| Mode | Best For |
|------|----------|
| `popular` | Finding proven sellers for that keyword |
| `newest` | Finding fresh designs related to that keyword |
| `relevant` | Using Roblox's default relevance ranking |
| `random` | General exploration |

### Advanced Duplicate Detection
The tool includes an advanced duplicate detection system that combines multiple image hashing algorithms to effectively detect similar clothing items.

#### How It Works
1. Uses 5 different perceptual hash algorithms:
   - **Perceptual Hash (pHash)**: Good at detecting structural similarities
   - **Difference Hash (dHash)**: Good at detecting gradient changes
   - **Average Hash (aHash)**: Simple but effective for many cases
   - **Wavelet Hash (wHash)**: Good at detecting significant visual features
   - **Color Hash**: Detects similarities in color distribution
2. Compares new images to all existing images in your assets folder
3. Considers an image a duplicate if at least `min_algorithm_matches` (configurable) algorithms detect similarity

Configuration Example:
```json
{
    "duplicate_detection": {
        "use_advanced": true,
        "min_algorithm_matches": 2,
        "thresholds": {
            "phash": 3,
            "dhash": 3,
            "ahash": 5,
            "whash": 3,
            "colorhash": 4
        }
    }
}
```

#### Sensitivity Adjustment
For **stricter** detection (more matches, possible false positives):
- Lower threshold values (e.g., `phash: 2`)
- Decrease `min_algorithm_matches` (e.g., `1`)

For **more lenient** detection (only very similar images):
- Increase threshold values (e.g., `phash: 5`)
- Increase `min_algorithm_matches` (e.g., `3` or `4`)

### Duplicate Upload Prevention
The tool uses an upload log system to prevent uploading identical assets multiple times.

#### How It Works
1. **Central Log**: Uses `src/assets/upload_logs/upload_log.txt` to track successful uploads
2. **Image Fingerprinting**: Calculates SHA256 hash of each image file
3. **Success Logging**: Records Group ID and image hash on successful upload
4. **Pre-Upload Check**: Verifies against log before attempting new uploads

Example log entry:
```text
1234567,a1b2c3d4e5f6...
```
This system prevents wasting Robux on duplicate uploads across different sessions.
