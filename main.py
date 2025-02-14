from fastapi import FastAPI, HTTPException
import yt_dlp


app = FastAPI()


@app.get("/download")
def download_video(url: str):
    """
    Test endpoint: Downloads a YouTube video using yt-dlp.

    Example usage:
    GET /download?url=https://www.youtube.com/watch?v=VIDEO_ID
    """
    try:
        ydl_opts = {"format": "bestvideo+bestaudio",
                    "cookies_from_browser": "chrome",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
                    "force_ipv4": True
                    }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)  # Download video
        return {"message": "Download complete", "title": info["title"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error downloading video: {str(e)}")
