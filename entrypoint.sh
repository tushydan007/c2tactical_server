#!/bin/bash
set -e

# Only the "backend" container is allowed to run migrations and collectstatic
if [ "$DJANGO_ROLE" != "worker" ]; then
  echo "Waiting for PostgreSQL..."
  while ! nc -z db 5432; do
    sleep 0.1
  done
  echo "PostgreSQL started"

  echo "Running migrations..."
  python manage.py migrate --noinput

  echo "Collecting static files..."
  python manage.py collectstatic --noinput --clear

  echo "Creating superuser if not exists..."
  python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@c2tactical.com').exists():
    User.objects.create_superuser(
        email='admin@c2tactical.com',
        password='admin123',
        first_name='Admin',
        last_name='User'
    )
    print("Superuser created")
else:
    print("Superuser already exists")
EOF
else
  echo "Worker container - skipping migrations, collectstatic and superuser creation"
fi

# Always wait again for DB (celery needs it too)
while ! nc -z db 5432; do
  sleep 0.1
done

exec "$@"