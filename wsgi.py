import sys
import os
from pathlib import Path

# Sesuaikan path root project di PythonAnywhere, misal: /home/<username>/aqua_ews_dashboard
PROJECT_DIR = os.environ.get("EWS_BASE_DIR", str(Path(__file__).resolve().parent))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("EWS_BASE_DIR", PROJECT_DIR)

from app import app as application  # WSGI entrypoint