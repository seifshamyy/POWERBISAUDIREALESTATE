# Use official Python image with Playwright support
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps

# Copy application code
COPY . .

# Expose port
ENV PORT=8000
EXPOSE $PORT

# Run the application using the PORT environment variable
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
