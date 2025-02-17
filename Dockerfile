# Use Python 3.10 as the base image
FROM python:3.10

# Set working directory
WORKDIR /app

# Copy all application files
COPY . /app

# Install system dependencies required for Playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgtk-3-0 \
    libxcomposite1 \
    libxrandr2 \
    libappindicator3-1 \
    libpango1.0-0 \
    libxcursor1 \
    libxdamage1 \
    fonts-liberation \
    xvfb && \
    rm -rf /var/lib/apt/lists/*  # Corrected placement of `&&`

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and required browsers
RUN pip install playwright && playwright install --with-deps

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV DISPLAY=:99  # Set Virtual Display

# Expose FastAPI port
EXPOSE 8000

# Start Xvfb first, then run FastAPI
CMD Xvfb :99 -screen 0 1024x768x16 & uvicorn main:app --host 0.0.0.0 --port 8000
