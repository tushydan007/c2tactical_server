#!/bin/bash
set -e

echo "=== Django Startup Script ==="

# Wait for PostgreSQL
echo "Waiting for database (db:5432)..."
while ! nc -z db 5432; do
  sleep 1
done
echo "PostgreSQL is up!"

# Only run makemigrations if there are unapplied migration files in your apps
echo "Checking for new migrations..."
if python manage.py makemigrations --dry-run --check | grep -q "No changes detected"; then
  echo "No new migrations needed."
else
  echo "New migrations detected → creating them..."
  python manage.py makemigrations --no-input
fi

# Always run migrate (it's safe and fast even if nothing to apply)
echo "Applying database migrations..."
python manage.py migrate --no-input

# Optional: collect static files only if they changed (idempotent anyway)
echo "Collecting static files..."
python manage.py collectstatic --no-input --clear || true

echo "=== Startup complete. Starting application... ==="

# Execute the command passed to the container (gunicorn, runserver, celery, etc.)
exec "$@"