"""Django storage backend backed by Supabase Storage's REST API.

This avoids S3 access keys: the bucket is read through its public URL, while
writes/deletes require the project's publishable key plus a private header that
is enforced by a Row Level Security policy on ``storage.objects``.

Required environment variables:
  SUPABASE_URL
  SUPABASE_ANON_KEY
  SUPABASE_STORAGE_ACCESS_TOKEN
  SUPABASE_STORAGE_BUCKET
"""

import mimetypes
import os
from urllib.parse import quote

import requests
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class SupabaseStorage(Storage):
    """Store Django files in a Supabase Storage bucket."""

    def __init__(
        self,
        base_url=None,
        bucket_name=None,
        api_key=None,
        access_token=None,
        timeout=60,
    ):
        self.base_url = (base_url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.bucket_name = bucket_name or os.getenv("SUPABASE_STORAGE_BUCKET", "talentflow-media")
        self.api_key = api_key or os.getenv("SUPABASE_ANON_KEY", "")
        self.access_token = access_token or os.getenv("SUPABASE_STORAGE_ACCESS_TOKEN", "")
        self.timeout = timeout

        if not self.base_url or not self.api_key or not self.access_token:
            raise ImproperlyConfigured(
                "SupabaseStorage needs SUPABASE_URL, SUPABASE_ANON_KEY and "
                "SUPABASE_STORAGE_ACCESS_TOKEN."
            )

    # -- helpers ---------------------------------------------------------
    def _object_url(self, name):
        return (
            f"{self.base_url}/storage/v1/object/{self.bucket_name}/"
            f"{quote(name, safe='/')}"
        )

    def _public_url(self, name):
        return (
            f"{self.base_url}/storage/v1/object/public/{self.bucket_name}/"
            f"{quote(name, safe='/')}"
        )

    @property
    def _write_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "x-talentflow-storage-key": self.access_token,
        }

    def _check(self, response, action):
        if response.status_code in (200, 201, 204):
            return
        if response.status_code == 404 and action in ("delete", "open"):
            raise FileNotFoundError(f"Supabase Storage object not found: {response.url}")
        raise OSError(
            f"Supabase Storage {action} failed ({response.status_code}): "
            f"{response.text[:300]}"
        )

    # -- Storage API -----------------------------------------------------
    def _save(self, name, content):
        content_type = getattr(content, "content_type", None)
        if not content_type:
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        response = requests.post(
            self._object_url(name),
            data=content.read(),
            headers={
                **self._write_headers,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            timeout=self.timeout,
        )
        self._check(response, "upload")
        return name

    def _open(self, name, mode="rb"):
        response = requests.get(self._public_url(name), timeout=self.timeout)
        self._check(response, "open")
        return ContentFile(response.content, name=name)

    def exists(self, name):
        response = requests.head(self._public_url(name), timeout=self.timeout)
        return response.status_code == 200

    def size(self, name):
        response = requests.head(self._public_url(name), timeout=self.timeout)
        self._check(response, "open")
        return int(response.headers.get("content-length", 0))

    def url(self, name):
        return self._public_url(name)

    def delete(self, name):
        response = requests.delete(
            self._object_url(name),
            headers=self._write_headers,
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return
        self._check(response, "delete")
