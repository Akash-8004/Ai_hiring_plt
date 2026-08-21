"""Cloudflare R2 storage service for interview recordings.

Uploads recordings to R2 (S3-compatible) and always saves a local copy
to ``temp_files/`` for development and testing.
"""

import os
import time
from pathlib import Path

import boto3
from botocore.config import Config

TEMP_DIR = Path(__file__).resolve().parent.parent.parent / "temp_files"
TEMP_DIR.mkdir(exist_ok=True)
HR_TEMP_DIR = TEMP_DIR / "hr"
HR_TEMP_DIR.mkdir(exist_ok=True)


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_configured() -> bool:
    """Return True when all required R2 environment variables are present."""
    return all(
        _env(key)
        for key in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
    )


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url = f"https://{_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_recording(
    email: str,
    interview_type: str,
    file_bytes: bytes,
) -> dict:
    """Upload a recording blob to R2 **and** save locally for testing.

    Returns a metadata dict suitable for persisting in MongoDB.
    """
    timestamp = int(time.time())
    safe_email = email.replace("@", "_at_").replace(".", "_")
    filename = f"{safe_email}_{interview_type}_{timestamp}.webm"
    r2_key = f"recordings/{filename}"

    size_bytes = len(file_bytes)
    # HR recordings are stored in a separate subdirectory
    target_dir = HR_TEMP_DIR if interview_type == "hr" else TEMP_DIR
    local_path = str(target_dir / filename)

    # Always save locally for testing
    Path(local_path).write_bytes(file_bytes)

    result = {
        "r2_key": r2_key,
        "filename": filename,
        "size_bytes": size_bytes,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "local_path": local_path,
    }

    # Upload to R2 when configured
    if is_configured():
        try:
            _s3_client().put_object(
                Bucket=_env("R2_BUCKET_NAME"),
                Key=r2_key,
                Body=file_bytes,
                ContentType="video/webm",
            )
        except Exception as exc:
            result["r2_error"] = str(exc)

    return result


def get_recording_presigned_url(r2_key: str, expires_in: int = 3600) -> str | None:
    """Generate a time-limited presigned GET URL for *r2_key*.

    Returns ``None`` when R2 is not configured or on error.
    """
    if not is_configured():
        return None
    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _env("R2_BUCKET_NAME"), "Key": r2_key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return None
