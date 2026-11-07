"""
Devengers Cloudinary Image Storage Service.
Zero external dependencies - built with Python standard library (urllib.request, json, hashlib, base64).

Provides permanent media storage for:
- User avatars & profile banners
- Event thumbnails & poster images
- Community showcase projects
- Certificate templates & logos

If Cloudinary environment variables are present, files are uploaded to Cloudinary CDN over HTTPS (port 443).
If not configured (e.g. local testing), falls back seamlessly to saving locally in Assest/uploads/.
"""

import os
import re
import time
import json
import base64
import hashlib
import secrets
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Tuple, Dict, Any

def get_cloudinary_config() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extracts Cloudinary credentials from environment variables.
    Supports CLOUDINARY_URL format: cloudinary://<api_key>:<api_secret>@<cloud_name>
    or individual CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET.
    """
    cloud_url = os.environ.get("CLOUDINARY_URL", "").strip()
    if cloud_url:
        match = re.match(r'^cloudinary:\/\/([^:]+):([^@]+)@([^\/]+)', cloud_url)
        if match:
            api_key, api_secret, cloud_name = match.groups()
            return cloud_name, api_key, api_secret

    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.environ.get("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

    if cloud_name and api_key and api_secret:
        return cloud_name, api_key, api_secret

    return None, None, None

def is_cloudinary_configured() -> bool:
    """Returns True if valid Cloudinary credentials exist."""
    cloud_name, api_key, api_secret = get_cloudinary_config()
    return bool(cloud_name and api_key and api_secret)

def upload_to_cloudinary(file_bytes: bytes, folder: str = "devengers", detected_ext: str = "png") -> Dict[str, Any]:
    """
    Performs a signed upload to Cloudinary's REST API.
    Returns dictionary with 'url', 'public_id', 'size', and 'format'.
    """
    cloud_name, api_key, api_secret = get_cloudinary_config()
    if not (cloud_name and api_key and api_secret):
        raise RuntimeError("Cloudinary is not configured in environment variables.")

    timestamp = str(int(time.time()))
    clean_folder = folder.strip("/ ") or "devengers"

    # Cloudinary requires signature string sorted alphabetically: folder, timestamp
    string_to_sign = f"folder={clean_folder}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(string_to_sign.encode("utf-8")).hexdigest()

    mime_types = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "svg": "image/svg+xml"
    }
    mime = mime_types.get(detected_ext.lower(), "image/png")
    b64_data = base64.b64encode(file_bytes).decode("ascii")
    data_uri = f"data:{mime};base64,{b64_data}"

    upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    post_params = {
        "file": data_uri,
        "api_key": api_key,
        "timestamp": timestamp,
        "signature": signature,
        "folder": clean_folder
    }

    encoded_data = urllib.parse.urlencode(post_params).encode("utf-8")
    req = urllib.request.Request(
        upload_url,
        data=encoded_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "DevengersPlatform/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            secure_url = data.get("secure_url") or data.get("url")
            return {
                "success": True,
                "url": secure_url,
                "public_id": data.get("public_id"),
                "format": data.get("format", detected_ext),
                "size": data.get("bytes", len(file_bytes)),
                "provider": "cloudinary"
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloudinary HTTP Error {e.code}: {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"Cloudinary Upload Error: {e}") from e

def save_media_file(file_bytes: bytes, detected_ext: str = "png", prefix: str = "img", folder: str = "devengers", uploads_dir: str = None) -> Dict[str, Any]:
    """
    Unified media saver:
    1. If Cloudinary is configured, uploads directly to Cloudinary CDN.
    2. Otherwise, saves to local uploads_dir and returns relative URL (e.g. Assest/uploads/xyz.png).
    """
    if is_cloudinary_configured():
        try:
            res = upload_to_cloudinary(file_bytes, folder=folder, detected_ext=detected_ext)
            print(f"[CLOUDINARY UPLOAD] Successfully uploaded to CDN: {res.get('url')}")
            return res
        except Exception as e:
            print(f"[CLOUDINARY ERROR] Upload to Cloudinary failed: {e}. Falling back to local storage.")

    # Local storage fallback
    if not uploads_dir:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_static = os.path.abspath(os.path.join(current_dir, "..", "okay-dev-vanilla"))
        if os.path.exists(os.path.join(candidate_static, "index.html")):
            uploads_dir = os.path.join(candidate_static, "Assest", "uploads")
        else:
            uploads_dir = os.path.join(current_dir, "Assest", "uploads")

    os.makedirs(uploads_dir, exist_ok=True)
    safe_name = f"{prefix}_{int(time.time())}_{secrets.token_hex(4)}.{detected_ext}"
    target_path = os.path.join(uploads_dir, safe_name)

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    rel_url = f"Assest/uploads/{safe_name}"
    return {
        "success": True,
        "url": rel_url,
        "filename": safe_name,
        "size": len(file_bytes),
        "provider": "local"
    }

