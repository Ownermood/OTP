FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so code changes do not invalidate the layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user; it owns the data and log directories.
RUN useradd --create-home --uid 1000 bot \
    && mkdir -p /app/data /app/logs \
    && chown -R bot:bot /app
USER bot

# Migrations run on every start, so a fresh volume is initialised automatically.
CMD ["sh", "-c", "alembic upgrade head && python main.py"]
