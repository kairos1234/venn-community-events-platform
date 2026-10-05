#!/usr/bin/env python
"""Django's command-line utility (migrate, runserver, test, seed_demo_data, ...)."""

import os
import sys

# Don't write .pyc bytecode files (__pycache__ folders) next to the source.
sys.dont_write_bytecode = True

SETUP_HELP = """
Run this from the folder that contains manage.py, inside the project's virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
    pip install -r requirements.txt
"""


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    try:
        import django
    except ImportError:
        sys.exit("Django is not installed for this Python (is the virtual environment active?)." + SETUP_HELP)
    # Checked up front so an older Django elsewhere on the machine gives a clear message
    # instead of an import error deep inside the settings.
    if django.VERSION < (6, 0):
        sys.exit(
            f"This project needs Django 6.0 or newer, but {sys.executable}\n"
            f"has Django {django.get_version()}." + SETUP_HELP
        )
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
