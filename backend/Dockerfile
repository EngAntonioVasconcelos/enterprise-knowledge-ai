# The backend (API, worker, scripts and tests) in one Linux image.
# Development uses it through infrastructure/dev/docker-compose.yml (the
# "backend" service, with this folder mounted over /app/backend); the same
# image is the base for production (Phase 10).
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

# Dependencies first: this layer is rebuilt only when requirements change.
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY . .

# Never run as root inside the container.
RUN useradd --create-home --uid 1000 eka && chown -R eka /app
USER eka

# container_env.py points localhost addresses of the .env file to the host
# machine, then runs the command.
ENTRYPOINT ["python", "scripts/container_env.py"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
