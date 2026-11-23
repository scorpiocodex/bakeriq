FROM python:3.11-slim

ARG UID=1000
ARG GID=1000

# System deps for psycopg2 build (if it falls back to source) and healthcheck tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with passed UID/GID — fixes WSL bind-mount permissions
RUN groupadd -g ${GID} app && useradd -m -u ${UID} -g ${GID} -s /bin/bash app

WORKDIR /app

# Copy requirements first to maximise Docker layer cache
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest
COPY --chown=app:app . .

USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]