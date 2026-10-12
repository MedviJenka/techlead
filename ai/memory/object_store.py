"""
Supabase Storage through its S3-compatible API.

The boto3 client is configured for Supabase's gateway, which is stricter than AWS S3:
path-style addressing, no aws-chunked checksums, and no batch DeleteObjects.
"""

import posixpath
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, Self

from app.core.logger import Logger

if TYPE_CHECKING:
    from settings import Settings


logger = Logger("object-store")


class ObjectStore(Protocol):
    def list_keys(self, prefix: str) -> list[str]: ...

    def download(self, key: str, path: Path) -> None: ...

    def upload(self, path: Path, key: str) -> None: ...

    def delete_prefix(self, prefix: str) -> None: ...


class S3ObjectStore:
    """One Supabase Storage bucket. The client is built on first use, so bad credentials only fail storage calls."""

    def __init__(self, bucket: str, endpoint_url: str, region: str, access_key_id: str, secret_access_key: str) -> None:
        self.bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    @classmethod
    def from_settings(cls, settings: "Settings") -> Self | None:
        """None when ``AI_MEMORY_BUCKET`` is unset (memory off); raises if the bucket is set but credentials are not."""
        if not settings.AI_MEMORY_BUCKET:
            return None
        missing = [
            name
            for name in (
                "SUPABASE_S3_STORAGE",
                "SUPABASE_REGION",
                "SUPABASE_S3_ACCESS_KEY_ID",
                "SUPABASE_S3_SECRET_ACCESS_KEY",
            )
            if not getattr(settings, name)
        ]
        if missing:
            raise ValueError(f"AI_MEMORY_BUCKET is set but {', '.join(missing)} are not")
        return cls(
            settings.AI_MEMORY_BUCKET,
            str(settings.SUPABASE_S3_STORAGE),
            str(settings.SUPABASE_REGION),
            str(settings.SUPABASE_S3_ACCESS_KEY_ID),
            str(settings.SUPABASE_S3_SECRET_ACCESS_KEY),
        )

    @cached_property
    def _client(self) -> Any:
        import boto3  # lazy: only processes that use memory pay for the import
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            config=Config(
                s3={"addressing_style": "path"},
                # botocore >= 1.36 sends aws-chunked trailing checksums by default; Supabase's gateway
                # cannot parse them ("InvalidRequest: must have required property 'Body'").
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self._client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def download(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(Bucket=self.bucket, Key=key, Filename=str(path))

    def upload(self, path: Path, key: str) -> None:
        # Supabase's CDN collapses '..' before the request reaches S3, breaking the boto3 signature.
        self._client.upload_file(Bucket=self.bucket, Key=posixpath.normpath(key), Filename=str(path))

    def delete_prefix(self, prefix: str) -> None:
        # DeleteObjects always sends an aws-chunked body, which Supabase rejects: delete one at a time.
        keys = self.list_keys(prefix)
        for key in keys:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        logger.fire("storage_prefix_deleted", bucket=self.bucket, prefix=prefix, objects=len(keys))
