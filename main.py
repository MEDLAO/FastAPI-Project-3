import re
import io
import random
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pydantic import BaseModel
import pdfplumber
import docx
from typing import List

app = FastAPI()


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_random_user_agent():
    return random.choice(USER_AGENTS)


def extract_emails(text: str):
    """
    Extract email addresses from plain text using regex.
    Supports:
    - Standard emails (name@example.com)
    - Hyphenated and numeric emails (sales-team-42@business.co.uk)
    - Emails inside brackets (<support@domain.com>)
    - Basic obfuscated emails (john[at]example[dot]com)
    """

    # Normalize text (fix brackets)
    text = text.replace("<", " ").replace(">", " ").replace("[", " ").replace("]", " ")

    # Standard email extraction
    email_pattern = r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    regex_emails = re.findall(email_pattern, text)

    # Obfuscated emails: [at], (at), {dot}, etc.
    obfuscated_pattern = r"\b([a-zA-Z0-9._%+-]+)\s*(?:\[|\(|{)?at(?:\]|\)|})?\s*([a-zA-Z0-9.-]+)\s*(?:\[|\(|{)?dot(?:\]|\)|})?\s*([a-zA-Z]{2,})\b"
    obfuscated_emails = [f"{match[0]}@{match[1]}.{match[2]}" for match in re.findall(obfuscated_pattern, text)]

    # Combine results and remove duplicates
    emails = list(set(regex_emails + obfuscated_emails))
    return emails


class TextRequest(BaseModel):
    text: str


@app.post("/extract-emails-from-text")
def extract_emails_from_text(request: TextRequest):
    """
    FastAPI endpoint to extract emails from plain text.
    """
    emails = extract_emails(request.text)
    return {"emails": emails}


def extract_emails_from_pdf(pdf_bytes) -> List[str]:
    """
    Extract emails from a PDF file (uploaded as bytes).
    """
    text = ""
    try:
        with pdfplumber.open(pdf_bytes) as pdf:
            for page in pdf.pages:
                extracted_text = page.extract_text()
                if extracted_text:
                    text += extracted_text + "\n"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading PDF: {str(e)}")

    return extract_emails(text)


def extract_emails_from_docx(docx_file: UploadFile) -> List[str]:
    """
    Extract emails from a DOCX file (uploaded as an UploadFile).
    """
    try:
        # Convert SpooledTemporaryFile to BytesIO
        docx_bytes = io.BytesIO(docx_file.file.read())

        # Open DOCX using python-docx
        doc = docx.Document(docx_bytes)

        # Extract text from paragraphs
        text = "\n".join([para.text for para in doc.paragraphs])

        if not text.strip():  # Check if the document is empty
            raise HTTPException(status_code=400, detail="No text found in the document.")

        return extract_emails(text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading DOCX: {str(e)}")


@app.post("/extract-emails-from-file")
async def extract_emails_from_file(file: UploadFile = File(...)):
    """
    API endpoint to extract emails from an uploaded PDF or DOCX file.
    """
    file_extension = file.filename.split(".")[-1].lower()

    if file_extension == "pdf":
        emails = extract_emails_from_pdf(file.file)
    elif file_extension == "docx":
        emails = extract_emails_from_docx(file)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Only PDF and DOCX are allowed.")

    return {"filename": file.filename, "emails": emails}


def fetch_html(url: str) -> str:
    """
    Fetch HTML content from a website.
    - Uses requests for static pages (Fastest).
    - Uses Playwright for JavaScript-heavy pages.
    """
    headers = {"User-Agent": get_random_user_agent()}

    try:
        # Try using requests (Fastest method)
        response = requests.get(url, headers=headers, timeout=10)

        # If response is valid and has enough content, return it
        if response.status_code == 200 and len(response.text) > 500:
            return response.text  # Return static HTML

        print("JavaScript detected, switching to Playwright...")

    except requests.RequestException as e:
        print(f"Requests failed: {e}")

    # If JavaScript is required, use Playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Headless mode for speed
            page = browser.new_page()
            page.goto(url, timeout=15000)  # Load website with JavaScript
            html = page.content()  # Get fully rendered HTML
            browser.close()
            return html  # Return dynamic HTML

    except Exception as e:
        return f"Playwright failed: {e}"


def extract_emails_from_html(html_content: str) -> List[str]:
    """
    Extract email addresses from raw HTML content.
    - Extracts emails inside <a href="mailto:...">
    - Extracts emails from visible text.
    - Detects obfuscated emails (john[at]example[dot]com).
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Extract emails from <a href="mailto:...">
    mailto_links = [
        a["href"].replace("mailto:", "").strip()
        for a in soup.find_all("a", href=True)
        if a["href"].startswith("mailto:")
    ]

    # Extract visible text from HTML
    text = soup.get_text(separator=" ")

    # Standard email regex
    email_pattern = r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    regex_emails = re.findall(email_pattern, text)

    # Obfuscated email pattern ([at], (at), {dot}, etc.)
    obfuscated_pattern = r"\b([a-zA-Z0-9._%+-]+)\s*(?:\[|\(|{)?at(?:\]|\)|})?\s*([a-zA-Z0-9.-]+)\s*(?:\[|\(|{)?dot(?:\]|\)|})?\s*([a-zA-Z]{2,})\b"
    obfuscated_emails = [f"{match[0]}@{match[1]}.{match[2]}" for match in re.findall(obfuscated_pattern, text)]

    # Combine results and remove duplicates
    emails = list(set(mailto_links + regex_emails + obfuscated_emails))

    # Remove invalid entries (e.g., URLs or incorrect data)
    valid_emails = [email for email in emails if "@" in email and "." in email.split("@")[-1]]

    return valid_emails


@app.get("/extract-emails-from-url")
def extract_emails_from_url(
        url: str = Query(..., title="Website URL",
                         description="URL of the website to scrape emails from")
):
    """
    API endpoint to extract emails from a given URL.
    """
    html_content = fetch_html(url)

    if "Playwright failed" in html_content:
        raise HTTPException(status_code=500, detail=f"Error loading page: {html_content}")

    emails = extract_emails_from_html(html_content)

    if not emails:
        raise HTTPException(status_code=404, detail="No emails found on the page.")

    return {"url": url, "emails": emails}
