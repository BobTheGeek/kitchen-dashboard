FROM python:3.13-slim@sha256:d3449c0493345868b09708d7056dce5edda3a75233ea86008fc80c934d355a10 AS base
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Chicago
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements.txt
COPY app ./app
COPY fixtures ./fixtures

# `docker build --target test .` gates every deploy: if this stage fails, nothing ships.
FROM base AS test
COPY requirements-dev.txt pyproject.toml ./
COPY tests ./tests
COPY house_tools ./house_tools
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements-dev.txt \
 && ruff check app tests house_tools && pytest -q

FROM base
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
RUN useradd --uid 10001 --no-create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/version', timeout=5)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
