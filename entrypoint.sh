#!/bin/bash

set -e

echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

echo "Checking for migrations..."
python manage.py showmigrations | grep "\[ \]" > /dev/null 2>&1
NEEDS_MIGRATION=$?

if [ $NEEDS_MIGRATION -eq 0 ]; then
    echo "Unapplied migrations found. Running migrations..."
    python manage.py makemigrations --noinput
    python manage.py migrate --noinput
    echo "Migrations completed"
else
    echo "All migrations are up to date"
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Creating superuser if not exists..."
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@example.com').exists():
    User.objects.create_superuser(
        email='admin@example.com',
        password='admin123',
        first_name='Admin',
        last_name='User'
    )
    print('Superuser created successfully')
else:
    print('Superuser already exists')
EOF

exec "$@"