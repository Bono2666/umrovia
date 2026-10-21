"""WSGI entrypoint untuk CloudLinux Passenger (shared hosting ksisolusi.com).

Letakkan file ini di PassengerAppRoot, yaitu: /home/<user>/apps/umrovia/passenger_wsgi.py
"""
import os
import sys
from pathlib import Path

APP_ROOT = str(Path(__file__).resolve().parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
