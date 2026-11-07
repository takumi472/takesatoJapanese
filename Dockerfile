FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn whitenoise Flask-Limiter

# Copy all project files
COPY . .

EXPOSE 8080
ENV PORT=8080

# Run with Gunicorn using run.py as the entry point
# --timeout 60, --keep-alive 5 to prevent Slowloris / DoS thread exhaustion
CMD exec gunicorn --bind :$PORT --workers 2 --threads 16 --timeout 60 --keep-alive 5 run:app