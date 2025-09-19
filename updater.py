import sys
import os
import tempfile
import requests
import threading
from packaging.version import Version, InvalidVersion
from PySide6.QtCore import QApplication
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from config_utils import (
    set_last_installed_version,
    set_update_available,
    get_last_installed_version
)
from version import __version__ 

GITHUB_USER = "J0ttenmiller"
GITHUB_REPO = "BatteryLevelDisplay"
INSTALLER_FILENAME = "BatteryLevelDisplayInstaller.exe"

_running_threads = []


def get_latest_github_release():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        r = requests.get(api_url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("tag_name", "").lstrip("v"), data
    except Exception:
        return None, None


def check_for_updates_async(callback=None, silent=False, parent=None):
    def worker():
        latest_version, data = get_latest_github_release()
        installed_version = __version__  

        update_available = False
        if latest_version:
            try:
                latest_v = Version(latest_version)
                installed_v = Version(installed_version)
            except InvalidVersion:
                latest_v = latest_version
                installed_v = installed_version

            update_available = latest_v > installed_v

        set_update_available(update_available)

        if callback:
            callback(latest_version, installed_version, update_available)

        if update_available and not silent and parent:
            install_update(parent, latest_version, data)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    _running_threads.append(t)


def install_update(parent, latest_version, release_data=None):
    current_version = __version__ 
    try:
        latest_v = Version(latest_version)
        current_v = Version(current_version)
    except InvalidVersion:
        latest_v = latest_version
        current_v = current_version

    if latest_v <= current_v:
        QMessageBox.information(parent, "No Updates", "You already have the latest version.")
        set_update_available(False)
        return

    reply = QMessageBox.question(
        parent,
        "Update Available",
        f"A new version ({latest_version}) is available.\n"
        f"You have {current_version}.\n\nWould you like to update now?",
        QMessageBox.Yes | QMessageBox.No
    )
    if reply != QMessageBox.Yes:
        return

    asset_url = None
    if release_data:
        for asset in release_data.get("assets", []):
            if asset.get("name") == INSTALLER_FILENAME:
                asset_url = asset.get("browser_download_url")
                break
    if not asset_url:
        QMessageBox.warning(parent, "Error", "Installer not found in latest GitHub release.")
        return

    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, INSTALLER_FILENAME)

    progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, parent)
    progress.setWindowTitle("Downloading Update")
    progress.setWindowModality(progress.WindowModal)
    progress.show()

    try:
        with requests.get(asset_url, stream=True) as download:
            download.raise_for_status()
            total = int(download.headers.get("content-length", 0))
            downloaded = 0
            with open(installer_path, "wb") as f:
                for chunk in download.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress.setValue(int(downloaded * 100 / total))
                        QApplication.processEvents()
                    if progress.wasCanceled():
                        progress.close()
                        return
        progress.setValue(100)
        progress.close()
    except Exception as e:
        progress.close()
        QMessageBox.warning(parent, "Download Error", str(e))
        return

    set_update_available(False)

    os.startfile(installer_path)
    if parent:
        parent.close()
    sys.exit()

def sync_stored_version_on_startup():
    stored_version = get_last_installed_version()
    if stored_version != __version__:
        set_last_installed_version(__version__)
        set_update_available(False)