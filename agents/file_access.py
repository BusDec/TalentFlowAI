"""Helpers for reading Django file fields that may live on remote storage.

Django's ``FieldFile.path`` only works for local filesystem storage. The
production deployment stores uploads in Supabase Storage (S3), so parsing
agents need a local copy of the bytes. ``local_path`` yields a real path and
cleans up the temporary file afterwards.
"""

import os
import shutil
import tempfile
from contextlib import contextmanager


@contextmanager
def local_path(field_file):
    """Yield a local filesystem path for ``field_file``.

    Local storage is used as-is. For remote storage the object is downloaded
    into a temporary file with the same extension, then removed on exit.
    """
    try:
        path = field_file.path
    except (NotImplementedError, AttributeError, ValueError):
        suffix = os.path.splitext(getattr(field_file, "name", "") or "")[1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            with field_file.open("rb") as source, open(tmp_path, "wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            yield tmp_path
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return

    yield path
