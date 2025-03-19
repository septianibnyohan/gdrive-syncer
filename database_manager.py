import datetime
import hashlib
import os
from pathlib import Path
from typing import Optional, Dict
from dateutil.parser import parse
from sqlalchemy.exc import IntegrityError
import logging

import database
from database import File, Session

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.session = Session()
        database.init_db()

    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime.datetime]:
        """Parse datetime string from Google Drive."""
        return parse(dt_str) if dt_str else None

    @staticmethod
    def _get_local_checksum(path: Path) -> Optional[str]:
        """Calculate MD5 checksum for local file."""
        if not path.exists():
            return None

        md5 = hashlib.md5()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5.update(chunk)
        return md5.hexdigest()

    @staticmethod
    def _get_file_modified_time(file_path: Path) -> Optional[datetime.datetime]:
        """Get the last modified time of a file."""
        if file_path.exists():
            mod_time = file_path.stat().st_mtime
            return datetime.datetime.utcfromtimestamp(mod_time)
        logger.warning("File does not exist: %s", file_path)
        return None

    def get_file_by_local_path(self, local_path: Path) -> Optional[File]:
        """Retrieve file record from the database by local path."""
        return self.session.query(File).filter_by(local_path=str(local_path)).first()

    def get_file_by_remote_id(self, remote_id: str) -> Optional[File]:
        """Retrieve file record from the database by remote ID."""
        return self.session.query(File).filter_by(remote_id=remote_id).first()

    def _prepare_file_attributes(
            self, item: Dict, path: Path, parent_id: int, item_type: str
    ) -> Dict:
        """Prepare attributes for File record creation/update."""
        checksum = None
        remote_size = None
        local_size = None

        if item_type != "folder":
            checksum = item.get("md5Checksum") or self._get_local_checksum(path)
            remote_size = int(item.get("size", 0))
            local_size = path.stat().st_size if path.exists() else 0

        return {
            "type": item_type,
            "local_path": str(path),
            "remote_id": item["id"],
            "parent_id": parent_id,
            "name": item["name"],
            "checksum": checksum,
            "last_modified_remote": self._parse_datetime(item.get("modifiedTime")),
            "last_modified_local": self._get_file_modified_time(path),
            "sync_status": "synced",
            "file_size": remote_size,
            "local_size": local_size,
        }

    def update_file_record(
            self, item: Dict, path: Path, parent_id: int, item_type: str
    ) -> File:
        """Update or create database record for a file/folder."""
        file_attrs = self._prepare_file_attributes(item, path, parent_id, item_type)
        remote_id = item["id"]

        # Check for existing record by remote_id
        existing_file = self.get_file_by_remote_id(remote_id)

        if existing_file:
            # Update existing record with new attributes
            for key, value in file_attrs.items():
                setattr(existing_file, key, value)
            self.session.commit()
            return existing_file
        else:
            # Create new record if none exists
            file_record = File(**file_attrs)
            self.session.add(file_record)
            self.session.commit()
            return file_record