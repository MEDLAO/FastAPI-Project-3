import re
import io
import random
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
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


async def fetch_html(url: str) -> str:
    """
    Fetch HTML content from a website.
    - Uses requests for static pages (Fastest).
    - Uses Playwright for JavaScript-heavy pages.
    """
    headers = {"User-Agent": get_random_user_agent()}

    try:
        # Try using requests first (Fastest method)
        response = requests.get(url, headers=headers, timeout=3)

        # If response is valid and has enough content, return it
        if response.status_code == 200 and len(response.text) > 500:
            return response.text  # Return static HTML

    except requests.RequestException:
        pass  # Ignore and switch to Playwright

    # If JavaScript is required, use Playwright (ASYNC version)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            print(f"Fetching: {url}")  # Debugging output

            # Load the page and wait for JavaScript to execute
            await page.goto(url, wait_until="networkidle", timeout=5000)

            # Ensure dynamic elements are loaded
            try:
                await page.wait_for_selector("body", timeout=5000)  # Ensure page is visible
            except:
                print("Warning: Page body not found.")

            # Scroll down to force lazy-loaded content to load
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)  # Wait for content to load

            # Extract fully rendered HTML
            html = await page.content()
            await browser.close()
            return html  # Return final dynamic HTML

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


async def fetch_emails_with_pseudo(url):
    """
    Extracts emails split between ::before, main text, and ::after pseudo-elements.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=5000)
            await page.wait_for_timeout(3000)

            all_elements = await page.query_selector_all("*")

            emails = []
            for element in all_elements:
                try:
                    before_content = await page.evaluate(
                        "(el) => window.getComputedStyle(el, '::before').content", element
                    )
                    after_content = await page.evaluate(
                        "(el) => window.getComputedStyle(el, '::after').content", element
                    )
                    main_text = await element.inner_text()

                    before_content = before_content.strip('"') if before_content not in ['none', '""'] else ''
                    after_content = after_content.strip('"') if after_content not in ['none', '""'] else ''

                    full_text = before_content + main_text + after_content
                    emails.extend(extract_emails(full_text))

                except Exception:
                    pass  # Ignore elements that cause errors

            await browser.close()
            return list(set(emails))

    except Exception as e:
        print(f"[ERROR] Playwright failed: {e}")
        return []


@app.get("/extract-emails-from-url")
async def extract_emails_from_url(url: str = Query(...)):
    """
    API endpoint to extract emails from a given URL.
    """
    html_content = await fetch_html(url)

    if "Playwright failed" in html_content:
        raise HTTPException(status_code=500, detail=f"Error loading page: {html_content}")

    standard_emails = extract_emails(html_content)
    pseudo_emails = await fetch_emails_with_pseudo(url)

    all_emails = list(set(standard_emails + pseudo_emails))

    if not all_emails:
        raise HTTPException(status_code=404, detail="No emails found on the page.")

    return {"url": url, "emails": all_emails}
