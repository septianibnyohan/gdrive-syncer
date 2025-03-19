# Google Drive Sync

A Python application for synchronizing files and folders between Google Drive and your local system. This tool keeps track of file changes using a SQLite database and efficiently manages sync operations.

## Features

- Two-way synchronization between Google Drive and local filesystem
- Support for Google Workspace documents (exports as PDF/XLSX)
- File change tracking with checksums and timestamps
- Database-driven synchronization status management
- Progress bars for file downloads
- Logging of sync operations

## Project Structure

```
drive_sync/
├── credentials.json        # Google API credentials (you must provide this)
├── token.json              # OAuth token (generated on first run)
├── database.py             # Database models and connection
├── database_manager.py     # Database operations manager
└── google_drive_sync.py    # Google Drive API interface and sync logic
```

## Requirements

- Python 3.6+
- SQLAlchemy
- Google API Client Library for Python
- python-dateutil
- tqdm (for progress bars)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd drive_sync
   ```

2. Install dependencies:
   ```bash
   pip install sqlalchemy google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dateutil tqdm
   ```

3. Set up Google Drive API:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the Google Drive API
   - Create OAuth 2.0 credentials
   - Download the credentials as `credentials.json` and place it in the project directory

## Configuration

Update the `LOCAL_FOLDER` in `google_drive_sync.py` to point to your desired local sync directory:

```python
LOCAL_FOLDER = Path("/path/to/your/sync/folder")
```

## Usage

Run the synchronization script:

```bash
python google_drive_sync.py
```

On the first run, it will open a browser window to authenticate with your Google account. After authentication, the token will be saved locally for future use.

To sync from a specific Google Drive folder, modify the `remote_folder_id` parameter in the script:

```python
if __name__ == "__main__":
    syncer = GoogleDriveSync()
    syncer.sync_folder_structure(remote_folder_id="your_folder_id_here")
```

## Database Schema

The application uses a SQLite database with two main tables:

### Files Table
- Tracks file metadata and sync status
- Stores local paths, remote IDs, checksums, and timestamps

### Sync History Table
- Logs sync operations (upload/download/delete)
- Records success/failure status and error messages

## How It Works

1. The application authenticates with Google Drive API
2. It recursively traverses the specified Google Drive folder structure
3. For each item:
   - If it's a folder, it creates the corresponding local folder
   - If it's a file, it checks if it needs to be downloaded based on modification times
   - It updates the database with the sync status and file metadata
4. Special handling for Google Workspace documents (Docs, Sheets, Slides) exports them to compatible formats

## Extending the Application

### Adding Upload Functionality

The current implementation focuses on downloading files from Google Drive. To add upload functionality, you would need to:

1. Create a method to scan local files
2. Compare them with database records
3. Use the `upload_file` method to push changes to Google Drive

### Implementing Delete Synchronization

To handle file deletions:

1. Add a method to check for files in the database that no longer exist locally or remotely
2. Mark them as deleted in the database
3. Optionally remove them from the other location

## Troubleshooting

- **Authentication Issues**: If you encounter authentication problems, delete `token.json` and run the script again
- **Database Errors**: Check the SQLite database file at `~/.config/gdrive_sync/files.db` for integrity
- **Sync Problems**: Set logging level to DEBUG for more detailed information about sync operations

## License

[Your license information here]

## Contributing

[Your contribution guidelines here]
