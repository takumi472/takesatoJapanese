FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn uvicorn

# Copy all project files
COPY . .

EXPOSE 8080
ENV PORT=8080

# Run with Gunicorn using Uvicorn worker for FastAPI
# (Change `run:app` to match your actual file and FastAPI instance variable, e.g., `main:app` or `app.main:app`)
CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0 run:app