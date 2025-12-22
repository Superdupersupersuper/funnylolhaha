FROM python:3.11-slim

# Install Chrome dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    unzip \
    curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create data directory
RUN mkdir -p /app/data

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (fallback)
RUN playwright install chromium || echo "Playwright install failed, will use Chrome"

# Copy application code
COPY . .

# Expose port
EXPOSE 10000

# Start command
CMD ["gunicorn", "-c", "gunicorn_config.py", "api_server:app"]

