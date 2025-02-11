from fastapi import FastAPI, HTTPException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time

app = FastAPI()


# Function to check if a WhatsApp number is valid
def is_whatsapp_number(phone_number: str) -> bool:
    """
    Uses Selenium to check if a phone number is registered on WhatsApp.
    """
    try:
        # Configure Chrome options (headless mode for performance)
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Set up WebDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # WhatsApp web URL to check the number
        whatsapp_url = f"https://api.whatsapp.com/send?phone={phone_number}"
        driver.get(whatsapp_url)

        # Wait for page to load
        time.sleep(3)

        # Check if "Chat with" appears (means the number is valid)
        page_source = driver.page_source
        if "Click to Chat" in page_source:
            driver.quit()
            return True  # WhatsApp number is valid

        driver.quit()
        return False  # WhatsApp number is not valid

    except Exception as e:
        return False  # Assume invalid if error occurs


# FastAPI endpoint
@app.get("/validate/")
def validate_whatsapp_number(phone_number: str):
    """
    API endpoint to check if a phone number is registered on WhatsApp.
    """
    if not phone_number.startswith("+"):
        raise HTTPException(status_code=400, detail="Phone number must include country code (e.g., +14155552671)")

    is_valid = is_whatsapp_number(phone_number)

    return {
        "phone_number": phone_number,
        "is_whatsapp": is_valid
    }
