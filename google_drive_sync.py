from drive_to_local_syncer import DriveLocalSyncer
from local_to_drive_syncer import LocalDriveSyncer
import time

if __name__ == "__main__":
    remote_id = '1Yk7WQFKvSbWaXTPTJT3n9_tZpbdsC_pV'  # obsidian

    # Initialize syncers once
    download_syncer = DriveLocalSyncer()
    upload_syncer = LocalDriveSyncer()

    while True:
        print(f"\nStarting sync at {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Drive-to-local sync
        print("Syncing Drive to local...")
        download_syncer.sync_folder_structure(remote_id)

        # Local-to-Drive sync
        print("Syncing local to Drive...")
        upload_syncer.sync_local_to_drive(remote_parent_id=remote_id)

        print(f"Sync completed. Next sync at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + 1800))}")
        time.sleep(1800)  # 30 minutes delay (1800 seconds)
