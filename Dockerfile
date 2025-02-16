# Step 1: Use an official Python base image
FROM python:3.10

# Step 2: Set the working directory in the container
WORKDIR /app

# Step 3: Copy all application files into the container
COPY . /app

# Step 4: Install system dependencies required for Playwright
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

# Step 5: Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Install Playwright and required browsers
RUN pip install playwright && playwright install --with-deps

# Step 7: Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# Step 8: Expose FastAPI port
EXPOSE 8000

# Step 9: Start FastAPI using the main.py file
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
