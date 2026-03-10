#!/usr/bin/env python3
"""
Git Release Fetcher v1.2b
Author: Dimitri Pappas <https://github.com/fragtion>
License: MIT

Retrieves a list of file assets for a given GitHub repo release and optionally downloads them.
If a specific release is not provided, the script defaults to the latest release.
Supports glob/wildcard filtering with --include and --exclude, resuming interrupted downloads,
and verifies downloaded file sizes by comparing with the release manifest as a simple sanity check.
"""

import os
import sys
import json
import time
import argparse
import fnmatch
import urllib.request
from urllib.error import HTTPError, URLError

VERSION = "v1.2b"
PROGRAM_NAME = "Github Release Fetcher"

def format_size(size):
    """Convert file size in bytes to a human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def format_speed(speed):
    """Format download speed into human-readable format."""
    if speed < 1024:
        return f"{speed:.2f} B/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.2f} KB/s"
    else:
        return f"{speed / (1024 * 1024):.2f} MB/s"

def format_eta(seconds):
    """Format remaining seconds into a human-readable ETA string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60)}m"

def download_file_with_progress(url, target_path, expected_size=None):
    """Download a file with progress bar, resume support, and ETA display."""
    try:
        if os.path.exists(target_path):
            existing_size = os.path.getsize(target_path)
            if expected_size and existing_size == expected_size:
                print(f"File already exists and matches expected size: \"{target_path}\"")
                return
            headers = {"Range": f"bytes={existing_size}-"}
            req = urllib.request.Request(url, headers=headers)
            mode = "ab"
        else:
            req = urllib.request.Request(url)
            mode = "wb"
            existing_size = 0

        with urllib.request.urlopen(req) as response, open(target_path, mode) as target_file:
            content_length = int(response.headers.get("Content-Length", 0))
            file_size = content_length + existing_size
            chunk_size = 1024 * 1024  # 1 MB chunks
            bytes_so_far = existing_size
            start_time = time.time()

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break

                target_file.write(chunk)
                bytes_so_far += len(chunk)

                elapsed_time = time.time() - start_time
                download_speed = (bytes_so_far - existing_size) / elapsed_time if elapsed_time > 0 else 0

                if file_size > 0:
                    percent_complete = (bytes_so_far / file_size) * 100
                    bar_length = 40
                    num_chars = int(percent_complete / (100 / bar_length))
                    bar = "#" * num_chars + "." * (bar_length - num_chars)

                    remaining_bytes = file_size - bytes_so_far
                    eta = format_eta(remaining_bytes / download_speed) if download_speed > 0 else "?"
                    progress = (
                        f"\r[{bar}] {int(percent_complete)}% "
                        f"{format_size(bytes_so_far)}/{format_size(file_size)} "
                        f"@ {format_speed(download_speed)} ETA {eta}"
                    )
                else:
                    progress = f"\rDownloaded {format_size(bytes_so_far)} @ {format_speed(download_speed)}"

                sys.stdout.write(progress)
                sys.stdout.flush()

            sys.stdout.write("\n")

        if expected_size and os.path.getsize(target_path) != expected_size:
            print(f"Error: File size mismatch for \"{target_path}\"")
        else:
            print(f"Done: \"{target_path}\"")

    except (HTTPError, URLError) as e:
        print(f"\nError: Failed to download \"{target_path}\" - {e}")
    except KeyboardInterrupt:
        print(f"\nInterrupted: \"{target_path}\" (partial download kept, resume supported)")
        sys.exit(1)

def fetch_release_data(repo_url, release_tag=None):
    """Fetch release data from GitHub API."""
    if repo_url.startswith("https://api.github.com/repos/"):
        parts = repo_url[len("https://api.github.com/repos/"):].split("/")
        if len(parts) < 2:
            print("Error: Invalid GitHub API URL.")
            sys.exit(1)
        owner, repo = parts[0], parts[1]

    elif repo_url.startswith("https://github.com/"):
        parts = repo_url[len("https://github.com/"):].split("/")
        if len(parts) < 2:
            print("Error: Invalid GitHub repository URL.")
            sys.exit(1)
        owner, repo = parts[0], parts[1]

        if "releases/tag/" in repo_url:
            url_release_tag = repo_url.split("releases/tag/")[-1].strip("/")
            if release_tag and release_tag != url_release_tag:
                print(
                    f"Error: Conflicting release tags. "
                    f"URL specifies '{url_release_tag}', but --release specifies '{release_tag}'."
                )
                sys.exit(1)
            release_tag = url_release_tag
    else:
        print("Error: Unsupported URL format. Please provide a GitHub repository or API URL.")
        sys.exit(1)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    api_url += f"/tags/{release_tag}" if release_tag else "/latest"

    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        if e.code == 404:
            print(f"Error: Release not found (404). Check the repo URL or release tag.")
        elif e.code == 403:
            print(f"Error: GitHub API rate limit exceeded (403). Try again later or use a token.")
        else:
            print(f"Error fetching release data: {e}")
        sys.exit(1)
    except URLError as e:
        print(f"Error: Could not reach GitHub API - {e}")
        sys.exit(1)

def filter_assets(assets, include=None, exclude=None):
    """Filter assets based on include/exclude glob pattern lists."""
    if include and exclude:
        print("Error: --include and --exclude are mutually exclusive.")
        sys.exit(1)

    if include:
        filtered = [asset for asset in assets if any(fnmatch.fnmatch(asset["name"], pat) for pat in include)]
        if not filtered:
            print(f"Warning: No assets matched the include pattern(s): {include}")
        return filtered
    elif exclude:
        return [asset for asset in assets if not any(fnmatch.fnmatch(asset["name"], pat) for pat in exclude)]
    else:
        return assets

def main():
    parser = argparse.ArgumentParser(
        description=(
            f"{PROGRAM_NAME} {VERSION} by Dimitri Pappas <https://github.com/fragtion>\n\n"
            "Fetch and download GitHub release assets with optional glob filtering.\n"
            "Supports resume, progress display, and release tag selection."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", help="GitHub repository or release URL")
    parser.add_argument("-r", "--release", help="Specific release tag (e.g., nightly, v1.0.0)")
    parser.add_argument("-d", "--download", action="store_true", help="Download matched release assets")
    parser.add_argument("-o", "--output", default=".", help="Output directory for downloaded files (default: .)")
    parser.add_argument(
        "-i", "--include", action="append", metavar="PATTERN",
        help="Only include assets matching PATTERN (glob, repeatable)\n  e.g. -i '*linux_amd64*' -i '*darwin*'"
    )
    parser.add_argument(
        "-e", "--exclude", action="append", metavar="PATTERN",
        help="Exclude assets matching PATTERN (glob, repeatable)\n  e.g. -e '*.sha256' -e '*.json'"
    )
    parser.add_argument(
        "-n", "--no-version-dir", action="store_true",
        help="Download directly into output dir, without a release tag subdirectory"
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {VERSION}")
    args = parser.parse_args()

    release_data = fetch_release_data(args.url, args.release)
    release_tag = release_data.get("tag_name", "unknown")
    assets = release_data.get("assets", [])

    if not assets:
        print(f"Release: {release_tag}")
        print("No assets found for this release.")
        sys.exit(0)

    assets = filter_assets(assets, args.include, args.exclude)

    print(f"Release: {release_tag}")
    print(f"Files ({len(assets)}):")
    for asset in assets:
        print(f"  {asset['name']} ({format_size(asset['size'])})")

    if args.download:
        if not assets:
            print("Nothing to download.")
            sys.exit(0)

        output_dir = args.output if args.no_version_dir else os.path.join(args.output, release_tag)
        os.makedirs(output_dir, exist_ok=True)
        print(f"\nDownloading {len(assets)} file(s) to: \"{output_dir}\"")

        for i, asset in enumerate(assets, 1):
            print(f"\n[{i}/{len(assets)}] {asset['name']} ({format_size(asset['size'])})")
            file_url = asset["browser_download_url"]
            file_path = os.path.join(output_dir, asset["name"])
            download_file_with_progress(file_url, file_path, asset["size"])

if __name__ == "__main__":
    main()
