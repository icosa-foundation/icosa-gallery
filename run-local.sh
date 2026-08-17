#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
REQUIREMENTS="$PROJECT_DIR/django/requirements.in"
INSTALL_MARKER="$VENV_DIR/.icosa-requirements-installed"
ICOSA_PYTHON="${ICOSA_PYTHON:-3.13}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv was not found. Install it from https://docs.astral.sh/uv/ and try again." >&2
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating the local Python environment with uv..."
    uv venv --python "$ICOSA_PYTHON" "$VENV_DIR"
fi

if [ ! -f "$INSTALL_MARKER" ] || [ "$REQUIREMENTS" -nt "$INSTALL_MARKER" ]; then
    echo "Installing Python dependencies with uv..."
    uv pip install --python "$VENV_DIR/bin/python" -r "$REQUIREMENTS"
    touch "$INSTALL_MARKER"
fi

if ! "$VENV_DIR/bin/python" -c 'import magic' >/dev/null 2>&1; then
    echo "The libmagic system library is required but was not found." >&2
    echo "Install it with 'brew install libmagic' on macOS or" >&2
    echo "'sudo apt install libmagic1' on Debian/Ubuntu, then try again." >&2
    exit 1
fi

export DEPLOYMENT_ENV="local"
export DEPLOYMENT_HOST_WEB="localhost:8000"
export DEPLOYMENT_HOST_API="localhost:8000"
export DEPLOYMENT_NO_SSL="1"
export DJANGO_DATABASE_ENGINE="sqlite"
export DJANGO_SQLITE_PATH="${DJANGO_SQLITE_PATH:-$PROJECT_DIR/django/db.local.sqlite3}"
export DJANGO_DISABLE_CACHE="1"
export DJANGO_IGNORE_ENFORCED_PERMISSIONS="1"
export DJANGO_SECRET_KEY="local-development-only-secret-key"
export JWT_SECRET_KEY="local-development-only-jwt-secret-key"

cd "$PROJECT_DIR/django"

if [ "$#" -eq 0 ] || [ "$1" != "migrate" ]; then
    echo "Preparing the SQLite database..."
    "$VENV_DIR/bin/python" manage.py migrate
    echo "Setting localhost:8000 as the default domain"
    "$VENV_DIR/bin/python" manage.py shell -c \
    "from django.contrib.sites.models import Site; Site.objects.filter(domain='example.com').update(domain='localhost:8000', name='localhost:8000')"
fi

if [ "$#" -gt 0 ]; then
    exec "$VENV_DIR/bin/python" manage.py "$@"
fi

echo "Starting Icosa Gallery at http://localhost:8000"
exec "$VENV_DIR/bin/python" manage.py runserver localhost:8000
