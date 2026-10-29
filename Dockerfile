# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY sentinel ./sentinel
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[redis]"

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels \
 && useradd --system --uid 10001 sentinel \
 && mkdir -p /app/data /app/models && chown -R sentinel /app
COPY config ./config
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"
ENV SENTINEL_POLICY=/app/config/policy.yaml SENTINEL_AUDIT_DB=/app/data/audit.db
CMD ["sentinel", "serve", "--host", "0.0.0.0", "--port", "8080"]
