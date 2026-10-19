FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy all project files
COPY . .

EXPOSE 8080
ENV PORT=8080

# Run with Gunicorn using run.py as the entry point
# (Change `app` to whatever your Flask instance variable is named inside run.py, e.g., `run:app`)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app