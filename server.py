import os
import uuid
import glob
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI(title="StreamFetch Render Backend")

# Allow requests from GitHub Pages or any frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cleanup_file(file_path: str):
    """Deletes temporary downloaded files after streaming to the user to save disk space."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


@app.get("/")
def health_check():
    """Health check endpoint so Render and the frontend know the server is awake."""
    return {"status": "online", "engine": "yt-dlp + ffmpeg"}


@app.get("/download")
def download_video(url: str, quality: str = "1080", background_tasks: BackgroundTasks = None):
    """
    Downloads and merges video + audio in the requested resolution (144, 360, 720, 1080, 1440, or audio).
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing YouTube URL")

    file_id = str(uuid.uuid4())[:8]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{file_id}_%(title)s.%(ext)s")

    # Select format string based on requested quality
    if quality == "audio":
        fmt = "bestaudio/best"
        ext = "m4a"
    else:
        fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
        ext = "mp4"

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": ext if quality != "audio" else None,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Find the generated file matching our unique file_id
            matching_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{file_id}_*"))
            if not matching_files:
                raise HTTPException(status_code=500, detail="Merged file not found on server.")
            
            final_path = matching_files[0]
            # Clean filename for the user's browser download
            clean_name = os.path.basename(final_path).split("_", 1)[1]

            # Schedule file deletion right after sending it to the user
            if background_tasks:
                background_tasks.add_task(cleanup_file, final_path)

            return FileResponse(
                path=final_path,
                filename=clean_name,
                media_type="application/octet-stream"
            )

    except Exception as e:
        # Clean up any partial files on failure
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"{file_id}_*")):
            cleanup_file(f)
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")