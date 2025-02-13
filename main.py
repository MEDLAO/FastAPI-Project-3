import os
import yt_dlp
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from pydantic import BaseModel
from starlette.responses import FileResponse, JSONResponse
from pyppeteer import launch


RAPIDAPI_SECRET = os.getenv("RAPIDAPI_SECRET")


app = FastAPI()


# Function to extract fresh YouTube cookies dynamically
async def get_youtube_cookies():
    try:
        browser = await launch(headless=True, args=["--no-sandbox"])
        page = await browser.newPage()
        await page.goto("https://www.youtube.com")

        cookies = await page.cookies()
        await browser.close()

        # Convert cookies to yt-dlp format
        return "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting cookies: {str(e)}")


# Middleware for enforcing RapidAPI authentication
# @app.middleware("http")
# async def enforce_rapidapi_usage(request: Request, call_next):
#     rapidapi_proxy_secret = request.headers.get("X-RapidAPI-Proxy-Secret")
#     if rapidapi_proxy_secret != RAPIDAPI_SECRET:
#         return JSONResponse(status_code=403, content={"error": "Access restricted to RapidAPI users only."})
#     return await call_next(request)


# Model for video info response
class VideoInfo(BaseModel):
    title: str
    duration: int
    uploader: str
    thumbnail: str


@app.get("/info")
async def get_video_info(url: str):
    try:
        cookies = await get_youtube_cookies()  # Extract fresh cookies dynamically
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "cookies": cookies
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info["title"],
            "duration": info["duration"],
            "uploader": info["uploader"],
            "thumbnail": info["thumbnail"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching video info: {str(e)}")


@app.get("/download")
def download_video(url: str):
    try:
        output_path = "downloads/%(title)s.%(ext)s"
        ydl_opts = {"format": "bestvideo+bestaudio", "outtmpl": output_path}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
        filename = ydl.prepare_filename(info)
        return FileResponse(filename, media_type="video/mp4", filename=os.path.basename(filename))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error downloading video: {str(e)}")


@app.get("/convert")
def convert_to_mp3(url: str):
    try:
        output_path = "downloads/%(title)s.%(ext)s"
        ydl_opts = {
            "format": "bestaudio",
            "outtmpl": output_path,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
        filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return FileResponse(filename, media_type="audio/mpeg", filename=os.path.basename(filename))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error converting video to MP3: {str(e)}")
