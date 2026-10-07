# github-release-fetcher
## Overview

**Github Release Fetcher** is a Python script that retrieves a list of files/assets for a given GitHub repository release and optionally downloads them.

If a specific release is not provided, the script defaults to the latest release.

It supports filtering files using `--include` and `--exclude`, resuming interrupted downloads, and verifies downloaded file sizes by comparing with the release manifest as a simple sanity check.

---

## Features

- **Fetch Release Assets**: Retrieve a list of files/assets for a GitHub repository release.
- **Download Files**: Optionally download the files to a specified directory.
- **Filter Files**: Use `--include` to download only specific files or `--exclude` to skip certain files.
- **Resume Downloads**: Supports resuming interrupted downloads — only when the remote file is confirmed unchanged (see below).
- **Replaced-Asset Detection**: If a maintainer updates/replaces an asset under the same release tag (common with rolling "nightly" releases), the old local copy is discarded and the new file is downloaded fresh. Previously this was either silently skipped (same-size replacement) or blind-appended via resume, producing a corrupt file.
- **File Size Verification**: Compares downloaded file sizes with the release manifest to help ensure integrity.
- **Human-Readable Output**: Displays file sizes in a human-readable format (e.g., KB, MB, GB).

### How updated/replace assets are detected

GitHub's release API reports each asset's `id` and `updated_at`. grf records these per asset in a `.grf-cache.json` file written next to the downloads. On a later run:

- Same asset id + same `updated_at` + matching size → the file is genuinely unchanged and gets skipped.
- Anything else (asset edited in place, deleted and re-uploaded, etc.) → the existing copy is replaced wholesale with a fresh download.
- Resume (`Range` requests) is only used for known-unchanged files, and the response's `Content-Range` header is verified before appending, so a server that ignores the range can no longer splice bytes onto an existing copy.

Keep `.grf-cache.json` alongside the downloaded files; if it is missing, existing copies cannot be trusted and are re-downloaded fresh.

---

## Installation

1. **Prerequisites**:
   - Python 3.x
   - `urllib` and `argparse` (included in Python's standard library)

2. **Download the Script**:
   - Clone this repository or download the `grf.py` script.

3. **Make the Script Executable** (Optional):
   ```bash
   chmod +x grf.py

## Usage

### Basic Usage

#### To fetch a list of files for the latest release:
`python3 grf.py https://github.com/owner/repo`

#### To download all files from the latest release:
`python3 grf.py https://github.com/owner/repo --download`

#### Specify a Release:
`python3 grf.py https://github.com/owner/repo --release nightly`, or `https://github.com/owner/repo/releases/tag/nightly`

#### Download to a Specific Directory:
`python3 grf.py https://github.com/owner/repo --download --output /path/to/directory`

#### Include Specific Files:
`python3 grf.py https://github.com/owner/repo --download --include file1.zip file2.zip`

#### Exclude Specific Files:
`python3 grf.py https://github.com/owner/repo --download --exclude file1.zip file2.zip`

#### Force Re-download (discard existing local copies):
`python3 grf.py https://github.com/owner/repo --download --force`

#### Show Version:
`python3 grf.py --version`

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contribution & Support
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

If you encounter any issues or have questions, feel free to open an issue on the GitHub repository.

## DISCLAIMER:
This project is still experimental, so reliability cannot be guaranteed, especially in production environments. Proceed at your own risk! It works great for me... but YMMV - proceed at own risk.

## Coffee

Did this make you happy? I'd love to do more development like this! Please donate to show your support :)

**PayPal**: [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/donate/?business=2CGE77L7BZS3S&no_recurring=0)

**BTC:** 1Q4QkBn2Rx4hxFBgHEwRJXYHJjtfusnYfy

**XMR:** 4AfeGxGR4JqDxwVGWPTZHtX5QnQ3dTzwzMWLBFvysa6FTpTbz8Juqs25XuysVfowQoSYGdMESqnvrEQ969nR9Q7mEgpA5Zm
