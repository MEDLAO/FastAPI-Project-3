# Use Python base image
FROM python:3.10

# Set working directory
WORKDIR /app

# Copy application files
COPY . /app

# Install system dependencies for Playwright
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
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its browsers
RUN pip install playwright && playwright install --with-deps

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
