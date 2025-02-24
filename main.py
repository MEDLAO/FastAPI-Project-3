import html
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
    - Obfuscated emails using [at], (at), {dot}, etc.
    - Obfuscations like "name at example dot com"
    - Hexadecimal encoding of email addresses
    - Reversed emails (moc.elpmaxe@eman)
    """

    # Decode HTML entities (for hex-encoded emails like &#110;&#97;...)
    text = html.unescape(text)

    # Normalize text (fix brackets & spaces)
    text = text.replace("<", " ").replace(">", " ")

    # 1. Standard email extraction
    email_pattern = r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
    regex_emails = re.findall(email_pattern, text)

    # 2. Obfuscated emails: [at], (at), {dot}, etc.
    obfuscated_pattern = r"\b([a-zA-Z0-9._%+-]+)\s*(?:\[|\(|{)?at(?:\]|\)|})?\s*([a-zA-Z0-9.-]+)\s*(?:\[|\(|{)?dot(?:\]|\)|})?\s*([a-zA-Z]{2,})\b"
    obfuscated_emails = [f"{match[0]}@{match[1]}.{match[2]}" for match in re.findall(obfuscated_pattern, text)]

    # 3. Obfuscated emails using `[@]`
    alt_obfuscated_pattern = r"\b([a-zA-Z0-9._%+-]+)\s*\[@\]\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    alt_obfuscated_emails = [f"{match[0]}@{match[1]}" for match in re.findall(alt_obfuscated_pattern, text)]

    # 4. Emails written as `name at example dot com`
    spaced_obfuscation_pattern = r"\b([a-zA-Z0-9._%+-]+)\s+at\s+([a-zA-Z0-9.-]+)\s+dot\s+([a-zA-Z]{2,})\b"
    spaced_obfuscated_emails = [f"{match[0]}@{match[1]}.{match[2]}" for match in re.findall(spaced_obfuscation_pattern, text)]

    # 5. Reversed emails (moc.elpmaxe@eman)
    reversed_email_pattern = r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    reversed_emails = [f"{match[0][::-1]}@{match[1][::-1]}" for match in re.findall(reversed_email_pattern, text[::-1])]

    # Combine results and remove duplicates
    emails = list(set(regex_emails + obfuscated_emails + alt_obfuscated_emails + spaced_obfuscated_emails + reversed_emails))
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


# Try fetching emails using requests (Static scraping)
def fetch_emails_static(url: str) -> List[str]:
    """
    Fetches emails from a static webpage using requests and BeautifulSoup.
    Returns emails if found, otherwise an empty list.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Requests failed: {e}")
        return []

    # Extract emails from raw text
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(separator=" ")
    emails = extract_emails(text)

    decoded_emails = list(extract_decoded_emails(soup))
    all_emails = list(set(emails + decoded_emails))
    if all_emails:
        print(f"[INFO] Emails found (Static): {all_emails}")

    return all_emails


# If static fails, try Playwright (Dynamic scraping + pseudo-elements)
async def fetch_emails_dynamic(url: str) -> List[str]:
    """
    Fetches emails from a JavaScript-rendered page using Playwright.
    If no emails are found, it also checks pseudo-elements (::before & ::after).
    """

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = await context.new_page()

            print(f"[INFO] Fetching dynamic content: {url}")
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(3000)  # Let the page fully render

            # Extract text content after JavaScript execution
            page_text = await page.evaluate("document.body.innerText")
            emails = extract_emails(page_text)

            # If no emails found, check pseudo-elements (::before & ::after)
            if not emails:
                elements = await page.query_selector_all("p, span, a, div")
                for element in elements:
                    try:
                        before = await page.evaluate(
                            "(el) => window.getComputedStyle(el, '::before').content", element
                        )
                        after = await page.evaluate(
                            "(el) => window.getComputedStyle(el, '::after').content", element
                        )
                        main_text = await element.inner_text()

                        # Remove unnecessary quotes around pseudo-elements
                        before = before.strip('"') if before not in ['none', '""'] else ''
                        after = after.strip('"') if after not in ['none', '""'] else ''

                        full_text = before + main_text + after
                        emails.extend(extract_emails(full_text))

                    except Exception:
                        pass  # Ignore missing pseudo-elements

            await browser.close()

            # Remove duplicates before returning
            emails = list(set(emails))
            if emails:
                print(f"[INFO] Emails found (Dynamic): {emails}")
            return emails

    except Exception as e:
        print(f"[ERROR] Playwright failed: {e}")
        return []


# Main function: Try static first, then Playwright if needed
async def fetch_emails(url: str) -> List[str]:
    """
    Orchestrates email extraction:
    Tries static scraping (requests)
    If static fails, tries dynamic scraping (Playwright)
    """
    emails = fetch_emails_static(url)

    if emails:
        return emails  # Found emails with static scraping

    # If no emails, try Playwright (JavaScript + pseudo-elements)
    return await fetch_emails_dynamic(url)


@app.get("/extract-emails")
async def extract_emails_from_url(url: str = Query(..., description="URL of the website")):
    """
    API endpoint to extract emails from a given URL.
    Tries static scraping first, then dynamic if needed.
    """
    emails = await fetch_emails(url)

    if not emails:
        raise HTTPException(status_code=404, detail="No emails found.")

    return {"url": url, "emails": emails}


def detect_shift(encoded_str):
    """
    Detects the most likely Caesar cipher shift used for obfuscation.
    It checks which shift produces recognizable email patterns.
    """
    for shift in range(1, 10):  # Test shifts from 1 to 10
        decoded_chars = [chr(ord(char) - shift) for char in encoded_str]
        decoded_email = "".join(decoded_chars)

        # Check if the decoded email contains common valid patterns
        if "@" in decoded_email and (".fr" in decoded_email or ".com" in decoded_email or ".edu" in decoded_email):
            return shift  # Return the detected shift value

    return 0  # Return 0 if no valid shift is found (fallback)


def decode_email(encoded_str):
    """
    Decodes an email obfuscated with an unknown shift.
    - Automatically detects the shift.
    - Applies necessary character replacements.
    - Ensures `.` stays correct in domains.
    """
    shift = detect_shift(encoded_str)  # Detect the correct shift
    if shift == 0:
        return encoded_str  # Return as-is if no shift detected

    # Reverse the detected shift
    decoded_chars = [chr(ord(char) - shift) for char in encoded_str]
    decoded_email = "".join(decoded_chars)

    # Replace obfuscated characters with proper symbols
    decoded_email = decoded_email.replace("[.", "@").replace("/", ".").replace("Z-", ".").replace("_", "-")

    # Automatically detect and fix username issues
    if "@" in decoded_email:
        username, domain = decoded_email.split("@")

        # If domain contains `.` and username has `.` but no `-`, assume `.` should be `-`
        if "." in domain and "." in username and "-" not in username:
            username = username.replace(".", "-")

        decoded_email = f"{username}@{domain}"

    # Remove unwanted `mailto*` prefixes if present
    decoded_email = re.sub(r'^mailto\*', '', decoded_email)

    return decoded_email


def extract_decoded_emails(soup_var):

    encrypted_emails = set()

    # 1. Extract standard mailto: links
    for mailto_link in soup_var.find_all('a', href=True):
        href = mailto_link['href']
        if href.startswith('mailto:'):
            email = href.replace('mailto:', '').strip()
            encrypted_emails.add(email)

    # 2. Extract obfuscated emails inside <a href="javascript:linkTo_UnCryptMailto('encoded_string')">
    for a_tag in soup_var.find_all('a', href=True):
        href = a_tag['href']
        if "javascript:linkTo_UnCryptMailto" in href:
            match = re.search(r"linkTo_UnCryptMailto\('([^']+)'\)", href)
            if match:
                encoded_str = match.group(1)
                decoded_email = decode_email(encoded_str)
                encrypted_emails.add(decoded_email)

    return encrypted_emails
