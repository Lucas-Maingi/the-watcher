FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY watcher ./watcher
RUN pip install --no-cache-dir ".[connectors,api,agent]"
# bake the demo graph so the container is demoable with zero setup
RUN watcher ingest --demo
EXPOSE 8000
CMD ["uvicorn", "watcher.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
