FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
# El mismo artefacto corre como API central (app:app) o API sync (sync_app:app); ver compose.yaml.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
