import io
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pytube import YouTube


# Initialize FastAPI app
app = FastAPI()


RAPIDAPI_SECRET = os.getenv("RAPIDAPI_SECRET")


# @app.middleware("http")
# async def enforce_rapidapi_usage(request: Request, call_next):
#     rapidapi_proxy_secret = request.headers.get("X-RapidAPI-Proxy-Secret")
#
#     if rapidapi_proxy_secret != RAPIDAPI_SECRET:
#         return JSONResponse(status_code=403, content={"error": "Access restricted to RapidAPI users only."})
#
#     return await call_next(request)


@app.get("/info")
def get_video_info(url: str):
    """
    Get video details (title, duration, uploader, and thumbnail).
    No download occurs here, only metadata is returned.

    Example usage:
    GET /info?url=https://www.youtube.com/watch?v=VIDEO_ID
    """
    try:
        yt = YouTube(url)  # Create a YouTube object from the given URL
        return {
            "title": yt.title,  # Video title
            "duration": yt.length,  # Video duration in seconds
            "uploader": yt.author,  # YouTube channel name
            "thumbnail": yt.thumbnail_url  # Video thumbnail image URL
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching video info: {str(e)}")


@app.get("/download")
def download_video(url: str):
    """
    Downloads the highest quality MP4 video from YouTube.

    Example usage:
    GET /download?url=https://www.youtube.com/watch?v=VIDEO_ID
    """
    try:
        video_caller = YouTube(url)  # Create YouTube object
        print(video_caller.title)  # Print video title

        # Select highest resolution progressive MP4 stream (video + audio)
        video_caller.streams.filter(progressive=True, file_extension='mp4') \
            .order_by('resolution').desc().first().download()

        print("Done!!")  # Print confirmation when download is complete

        return {"message": "Download complete", "title": video_caller.title}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error downloading video: {str(e)}")


@app.get("/convert")
def convert_to_mp3(url: str):
    """
    Extract and stream YouTube audio as an MP3 file.
    The file is NOT stored—it streams directly.

    Example usage:
    GET /convert?url=https://www.youtube.com/watch?v=VIDEO_ID
    """
    try:
        yt = YouTube(url)  # Initialize the YouTube object
        audio_stream = yt.streams.filter(only_audio=True).first()  # Get the best audio stream

        # Create an in-memory buffer to store the MP3
        audio_bytes = io.BytesIO()
        audio_stream.stream_to_buffer(audio_bytes)  # Download audio into memory
        audio_bytes.seek(0)  # Reset buffer to start position

        # Stream the MP3 file directly
        return StreamingResponse(audio_bytes, media_type="audio/mpeg",
                                 headers={
                                     "Content-Disposition": f"attachment; filename={yt.title}.mp3"})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error streaming MP3: {str(e)}")
