import datetime
import logging
from pathlib import Path
from typing import Dict

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm

import local_to_drive_syncer
from database_manager import DatabaseManager
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


class DriveLocalSyncer:
    def __init__(self):
        self.service = self.authenticate()
        self.db_manager = DatabaseManager()

    def sync_folder_structure(self, remote_folder_id: str = "root", local_parent: Path = local_to_drive_syncer.LOCAL_FOLDER):
        """Main entry point for Drive-to-local sync"""
        self._process_folder(remote_folder_id, local_parent, parent_id=0)

    def _process_folder(self, remote_folder_id: str, local_path: Path, parent_id: int):
        """Process folder and its contents"""
        items = self.service.files().list(
            q=f"'{remote_folder_id}' in parents",
            fields="files(id, name, mimeType, modifiedTime, md5Checksum, size)"
        ).execute().get("files", [])

        for item in items:
            item["mimeType"] == "application/vnd.google-apps.folder" \
            and self._process_folder_item(item, local_path, parent_id) \
            or self._process_file_item(item, local_path, parent_id)

    def _process_folder_item(self, item: Dict, local_path: Path, parent_id: int):
        """Handle folder items"""
        folder_path = local_path / item["name"]
        folder_path.mkdir(parents=True, exist_ok=True)
        db_folder = self.db_manager.update_file_record(item, folder_path, parent_id, "folder")
        self._process_folder(item["id"], folder_path, db_folder.id)

    def _process_file_item(self, item: Dict, local_path: Path, parent_id: int):
        """Handle file items"""
        file_path = local_path / item["name"]
        self._needs_update(item, file_path) and self._download_file(item, local_path, parent_id)

    def _download_file(self, item: Dict, local_path: Path, parent_id: int):
        """Download and update file record"""
        try:
            downloaded_path = self._perform_download(
                item["id"], item["name"], local_path, item["mimeType"]
            )

            self.db_manager.update_file_record(item, downloaded_path, parent_id, "file")
        except Exception as e:
            logger.error(f"Failed to download {item['name']}: {e}")

    def _perform_download(self, file_id: str, file_name: str, folder_path: Path, mime_type: str) -> Path:
        """Handle actual file download"""
        export_mime, extension = EXPORT_MIME_MAP.get(mime_type, (None, None))
        file_path = folder_path / f"{file_name}{extension if export_mime else ''}"

        request = self.service.files().export_media(fileId=file_id, mimeType=export_mime) if export_mime \
            else self.service.files().get_media(fileId=file_id)

        with file_path.open("wb") as f:
            self._download_with_progress(request, f, file_name)

        return file_path

    @staticmethod
    def _download_with_progress(request, file_handle, file_name: str):
        """Download with progress visualization"""
        downloader = MediaIoBaseDownload(file_handle, request)
        with tqdm(total=100, desc=f"Downloading {file_name}", unit="%", bar_format="{l_bar}{bar}| {n_fmt}%") as pbar:
            done = False
            while not done:
                status, done = downloader.next_chunk()
                status and pbar.update(int(status.progress() * 100) - pbar.n)

    def _needs_update(self, item: Dict, local_path: Path) -> bool:
        """Check if file needs update"""
        if not local_path.exists():
            return True

        remote_mtime = self.db_manager._parse_datetime(item.get("modifiedTime"))
        local_mtime = datetime.datetime.utcfromtimestamp(local_path.stat().st_mtime)

        local_size = local_path.stat().st_size if local_path.exists() else 0
        remote_size = int(item.get("size", 0))

        logger.info(f'remote size : {remote_size}, local size : {local_size}')
        if remote_size <= local_size:
            return False

        return (remote_mtime.replace(tzinfo=None) if remote_mtime.tzinfo else remote_mtime) > local_mtime

    @staticmethod
    def authenticate():
        """Authentication handler"""
        creds = None
        if Path("token.json").exists():
            creds = Credentials.from_authorized_user_file("token.json", local_to_drive_syncer.SCOPES)

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", local_to_drive_syncer.SCOPES)
            creds = flow.run_local_server(port=33749, access_type="offline", prompt="consent")
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        return build("drive", "v3", credentials=creds)