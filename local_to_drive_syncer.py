import datetime
import logging
import mimetypes
import os
from pathlib import Path
from typing import Dict
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from database_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
LOCAL_FOLDER = Path("/home/septian/gdrive_sync")


class LocalDriveSyncer:
    def __init__(self):
        logger.info("Initializing LocalDriveSyncer")
        self.service = self.authenticate()
        self.db_manager = DatabaseManager()
        logger.info("LocalDriveSyncer initialized")

    def sync_local_to_drive(self, local_folder: Path = LOCAL_FOLDER, remote_parent_id: str = None):
        """Main entry point for local-to-Drive sync"""
        remote_parent_id = remote_parent_id or "root"
        logger.info("Starting local-to-Drive sync. Local folder: %s, Remote parent ID: %s",
                    local_folder, remote_parent_id)
        self._sync_local_folder(local_folder, remote_parent_id)
        logger.info("Local-to-Drive sync completed")

    def _sync_local_folder(self, local_path: Path, remote_parent_id: str):
        """Process a folder and its contents for sync"""
        logger.info("Processing folder: %s", local_path)
        try:
            folder_record_remote_id = remote_parent_id
            if local_path != LOCAL_FOLDER:
                folder_record = self._get_or_create_folder(local_path, remote_parent_id)
                logger.debug("Folder record obtained: %s", folder_record)
                folder_record_remote_id = folder_record.remote_id


            logger.info("Processing items in folder: %s", local_path)
            self._process_folder_items(local_path, folder_record_remote_id)
            logger.info("Finished processing folder: %s", local_path)
        except Exception as e:
            logger.error("Error syncing folder %s: %s", local_path, e, exc_info=True)

    def _get_or_create_folder(self, local_path: Path, remote_parent_id: str):
        """Get existing or create new folder record"""
        folder_record = self.db_manager.get_file_by_local_path(local_path)
        if folder_record:
            logger.info("Found existing folder record for %s (ID: %s)",
                        local_path, folder_record.remote_id)
            return folder_record

        logger.info("Creating new folder: %s under parent ID %s",
                    local_path.name, remote_parent_id)
        folder_metadata = {
            'name': local_path.name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [remote_parent_id]
        }
        created_folder = self.service.files().create(body=folder_metadata, fields='id').execute()
        logger.info("Created new folder on Drive. ID: %s", created_folder['id'])
        return self._update_folder_record(local_path, created_folder['id'])

    def _update_folder_record(self, local_path: Path, remote_id: str):
        """Update database with folder information"""
        logger.debug("Updating folder record for %s with remote ID %s", local_path, remote_id)
        parent_record = self.db_manager.get_file_by_local_path(local_path.parent)
        logger.debug("Parent folder record: %s", parent_record.id if parent_record else "None")

        remote_folder = self.service.files().get(
            fileId=remote_id, fields='id, name, mimeType, modifiedTime'
        ).execute()
        logger.debug("Retrieved remote folder info: %s", remote_folder)

        updated_record = self.db_manager.update_file_record(
            remote_folder, local_path,
            parent_record.id if parent_record else None, "folder"
        )
        logger.info("Updated folder record in database for %s", local_path)
        return updated_record

    def _process_folder_items(self, local_path: Path, remote_folder_id: str):
        """Process all items in a folder"""
        items = list(local_path.iterdir())
        logger.info("Processing %d items in folder: %s", len(items), local_path)
        for item in items:
            logger.debug("Processing item: %s", item.name)
            if item.is_dir():
                self._sync_local_folder(item, remote_folder_id)
            else:
                self._sync_local_file(item, remote_folder_id)

    def _sync_local_file(self, local_file_path: Path, remote_parent_id: str):
        """Sync individual file to Drive"""
        logger.info("Syncing file: %s", local_file_path)
        try:
            file_record = self.db_manager.get_file_by_local_path(local_file_path)
            if file_record:
                logger.debug("Found existing file record (ID: %s)", file_record.remote_id)
                self._update_existing_file(file_record, local_file_path)
            else:
                logger.info("No existing record found. Uploading new file")
                self._upload_new_file(local_file_path, remote_parent_id)
        except Exception as e:
            logger.error("Error syncing file %s: %s", local_file_path, e, exc_info=True)

    def _update_existing_file(self, file_record, local_file_path):
        """Update existing file on Drive"""
        logger.info("Checking if file needs update: %s", local_file_path)
        if self._needs_update(file_record, local_file_path):
            logger.info("File needs update. Updating: %s", local_file_path)
            media = self._create_media_upload(local_file_path)
            logger.debug("Created media upload for file update")

            updated_file = self.service.files().update(
                fileId=file_record.remote_id, media_body=media,
                fields='id, name, modifiedTime'
            ).execute()
            logger.info("File updated on Drive. New modified time: %s", updated_file.get('modifiedTime'))

            self.db_manager.update_file_record(
                updated_file, local_file_path, file_record.parent_id, "file"
            )
            logger.info("Database record updated for file: %s", local_file_path)
        else:
            logger.info("File is up-to-date. No update needed: %s", local_file_path)

    def _needs_update(self, file_record, local_file_path) -> bool:
        """Check if local file is newer than remote"""
        local_mtime = datetime.datetime.utcfromtimestamp(local_file_path.stat().st_mtime)
        remote_mtime = file_record.last_modified_remote

        local_size = local_file_path.stat().st_size if local_file_path.exists() else 0
        remote_size = file_record.file_size

        if remote_size >= local_size:
            return False

        logger.info("Update check for %s. Local mtime: %s, Remote mtime: %s",
                     local_file_path, local_mtime, remote_mtime)
        return local_mtime > remote_mtime

    def _upload_new_file(self, local_file_path: Path, remote_parent_id: str):
        """Upload new file to Drive"""
        logger.info("Starting upload of new file: %s to parent ID %s",
                    local_file_path.name, remote_parent_id)
        media = self._create_media_upload(local_file_path)
        file_metadata = {'name': local_file_path.name, 'parents': [remote_parent_id]}
        logger.debug("File metadata: %s", file_metadata)

        new_file = self.service.files().create(
            body=file_metadata, media_body=media,
            fields='id, name, mimeType, modifiedTime'
        ).execute()
        logger.info("File uploaded successfully. ID: %s", new_file['id'])

        self._update_new_file_record(local_file_path, new_file)
        logger.info("Database record created for new file: %s", local_file_path)

    def _create_media_upload(self, file_path: Path):
        """Create properly configured MediaFileUpload"""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        logger.debug("Detected MIME type %s for file %s", mime_type, file_path)
        return MediaFileUpload(
            str(file_path),
            mimetype=mime_type or 'application/octet-stream',
            resumable=True
        )

    def _update_new_file_record(self, local_path: Path, remote_file: Dict):
        """Update database with new file info"""
        logger.debug("Updating database with new file record for %s", local_path)
        parent_record = self.db_manager.get_file_by_local_path(local_path.parent)
        logger.debug("Parent record ID: %s", parent_record.id if parent_record else "None")

        self.db_manager.update_file_record(
            remote_file, local_path,
            parent_record.id if parent_record else None, "file"
        )
        logger.info("New file record created in database for %s", local_path)

    @staticmethod
    def authenticate():
        """Authentication handler"""
        logger.info("Starting authentication process")
        creds = None
        token_file = "token.json"

        if Path(token_file).exists():
            logger.debug("Found token file at %s", token_file)
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.info("Credentials loaded from token file")
        else:
            logger.warning("No token file found at %s", token_file)

        if not creds or not creds.valid:
            logger.info("Credentials invalid or expired. Starting OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            logger.debug("Starting local server for OAuth")
            creds = flow.run_local_server(port=33749, access_type="offline", prompt="consent")

            with open("token.json", "w") as token:
                token.write(creds.to_json())
            logger.info("New credentials obtained and saved to token.json")

        logger.info("Authentication successful")
        return build("drive", "v3", credentials=creds)