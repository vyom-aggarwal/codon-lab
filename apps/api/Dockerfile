# Python 3.12 per the agreed stack.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . .

# Installed from pyproject.toml rather than a duplicated list of pins. The
# duplicate drifted the moment httpx was promoted to a runtime dependency, and
# the container silently lacked it while the local venv had it.
RUN pip install --upgrade pip && pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "codonlab.main:app", "--host", "0.0.0.0", "--port", "8000"]
