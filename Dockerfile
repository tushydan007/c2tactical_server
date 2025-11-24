FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    python3-venv \
    postgresql-client \
    libpq-dev \
    build-essential \
    libspatialindex-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libgeos-dev \
    libproj-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Create and activate virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copy project
COPY . .

# Copy and set permissions for entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create necessary directories
RUN mkdir -p /app/media/satellite/original \
    /app/media/satellite/optimized \
    /app/media/satellite/thumbnails \
    /app/media/avatars \
    /app/staticfiles \
    /app/logs

# Create non-root user
RUN if id 1000 >/dev/null 2>&1; then \
        echo "User with UID 1000 already exists, using existing user"; \
        EXISTING_USER=$(id -nu 1000); \
        chown -R $EXISTING_USER:$EXISTING_USER /app /opt/venv; \
    else \
        useradd -m -u 1000 appuser && \
        chown -R appuser:appuser /app /opt/venv; \
        EXISTING_USER=appuser; \
    fi

# Switch to non-root user
USER 1000

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "config.wsgi:application"]