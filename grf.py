#!/usr/bin/env python3
"""
Git Release Fetcher v1.3
Author: Dimitri Pappas <https://github.com/fragtion>
License: MIT

Retrieves a list of file assets for a given GitHub repo release and optionally downloads them.
If a specific release is not provided, the script defaults to the latest release.
Supports glob/wildcard filtering with --include and --exclude, resuming interrupted downloads,
and verifies downloaded file sizes by comparing with the release manifest as a simple sanity check.
Release assets that maintainers update/replace under the same tag are detected via the manifest
(asset id + updated_at, recorded in .grf-cache.json next to the downloads) and re-downloaded
fresh, instead of being silently skipped (same-size replacement) or spliced onto an existing
copy through blind resume. Resume is only trusted when the server actually honors our
Range request (verified via Content-Range).
"""

import os
import sys
import json
import time
import argparse
import fnmatch
import urllib.request
from urllib.error import HTTPError, URLError

VERSION = "v1.3"
PROGRAM_NAME = "Github Release Fetcher"
CACHE_FILENAME = ".grf-cache.json"

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

def load_cache(cache_path):
    """Load the download-identity cache written by previous runs."""
    try:
        with open(cache_path) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "files": {}}

def save_cache(cache_path, cache):
    """Write the download-identity cache atomically (temp file + rename)."""
    tmp_path = cache_path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(cache, f, indent=2)
        os.replace(tmp_path, cache_path)
    except OSError as e:
        print(f"Warning: could not update cache file: {e}")

def download_file_with_progress(url, target_path, expected_size=None, same_remote=False,
                                remote_known=False, force=False, observed=None):
    """Download a file with progress bar, verified resume support, and ETA display.

    Handles release assets that maintainers update/replace under the same tag:
      - same_remote: manifest asset (id + updated_at) matches what we last downloaded.
      - remote_known: a cache record exists for this target path.
      - force: discard any existing copy and download fresh.
      - observed: optional dict updated with ETag/Last-Modified from the response.

    Resume is only attempted when the remote file is known-unchanged, and it is
    verified against the response's Content-Range before appending; if the
    server ignores our Range request, the download restarts from scratch
    instead of splicing bytes onto an existing copy.

    Returns one of: "skipped", "complete", "partial", "failed".
    """
    try:
        existing_size = os.path.getsize(target_path) if os.path.exists(target_path) else 0

        if existing_size:
            if force:
                print(f"Force re-download: \"{target_path}\"")
                os.remove(target_path)
                existing_size = 0
            elif existing_size == expected_size:
                if same_remote:
                    print(f"File already downloaded and unchanged: \"{target_path}\"")
                    return "skipped"
                if remote_known:
                    print(f"Remote file was updated/replaced; existing copy discarded and re-downloaded: \"{target_path}\"")
                else:
                    print(f"Existing copy has no download record; cannot verify it matches remote; re-downloading fresh: \"{target_path}\"")
                os.remove(target_path)
                existing_size = 0
            elif not same_remote:
                print(f"Remote file differs from existing copy ({format_size(existing_size)} vs {format_size(expected_size)}); restarting download fresh: \"{target_path}\"")
                os.remove(target_path)
                existing_size = 0

        if existing_size > 0:
            response = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": f"bytes={existing_size}-"}))
        else:
            response = urllib.request.urlopen(urllib.request.Request(url))

        try:
            if observed is not None:
                for header in ("ETag", "Last-Modified"):
                    value = response.headers.get(header)
                    if value:
                        observed[header] = value

            if existing_size > 0:
                content_range = response.headers.get("Content-Range", "")
                if response.status != 206 or not content_range.startswith(f"bytes {existing_size}-"):
                    print(f"\nServer did not honor resume range for \"{target_path}\"; restarting download fresh.")
                    response.close()
                    os.remove(target_path)
                    existing_size = 0
                    response = urllib.request.urlopen(urllib.request.Request(url))
                    mode = "wb"
                else:
                    mode = "ab"
            else:
                mode = "wb"

            with open(target_path, mode) as target_file:
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
        finally:
            response.close()

        final_size = os.path.getsize(target_path)
        if expected_size and final_size != expected_size:
            print(f"Error: File size mismatch for \"{target_path}\" ({format_size(final_size)} of {format_size(expected_size)}); partial download kept, resume supported")
            return "partial"

        print(f"Done: \"{target_path}\"")
        return "complete"

    except (HTTPError, URLError) as e:
        print(f"\nError: Failed to download \"{target_path}\" - {e}")
        return "failed"
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
            "Supports resume, progress display, release tag selection, and safe\n"
            "handling of assets that were updated/replaced under the same release tag."
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
    parser.add_argument(
        "-f", "--force", action="store_true",
        help="Discard existing local copies and re-download every matched asset"
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
        cache_path = os.path.join(output_dir, CACHE_FILENAME)
        cache = load_cache(cache_path)
        files_cache = cache["files"]
        print(f"\nDownloading {len(assets)} file(s) to: \"{output_dir}\"")

        for i, asset in enumerate(assets, 1):
            print(f"\n[{i}/{len(assets)}] {asset['name']} ({format_size(asset['size'])})")
            file_url = asset["browser_download_url"]
            file_path = os.path.join(output_dir, asset["name"])
            entry = files_cache.get(asset["name"], {})
            same_remote = bool(entry) and entry.get("asset_id") == asset.get("id") and entry.get("updated_at") == asset.get("updated_at")
            observed = {}
            status = download_file_with_progress(
                file_url,
                file_path,
                asset["size"],
                same_remote=same_remote,
                remote_known=bool(entry),
                force=args.force,
                observed=observed,
            )
            if status != "skipped":
                files_cache[asset["name"]] = {
                    "asset_id": asset.get("id"),
                    "updated_at": asset.get("updated_at"),
                    "size": asset.get("size"),
                    "etag": observed.get("ETag"),
                    "last_modified": observed.get("Last-Modified"),
                }
                save_cache(cache_path, cache)

if __name__ == "__main__":
    main()
