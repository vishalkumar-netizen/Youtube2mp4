import os
import uuid
import glob
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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


def cleanup_file(path: str):
    """Safely removes temporary files after download or failure."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def health_check():
    """Friendly status page so visiting the Render URL directly isn't confusing."""
    return """
    <html>
        <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div style="background: #1e293b; padding: 2rem; border-radius: 1rem; border: 1px solid #334155; max-width: 480px; text-align: center;">
                <h2 style="color: #10b981; margin-top: 0;">&#10004; Render Backend is Online!</h2>
                <p style="color: #cbd5e1; line-height: 1.5;">Your <b>yt-dlp + FFmpeg</b> engine is running properly.</p>
                <p style="color: #94a3b8; font-size: 0.9rem;">Copy this page's URL from your browser address bar and paste it into your <b>GitHub Pages</b> website to start downloading videos.</p>
            </div>
        </body>
    </html>
    """


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
        "geo_bypass": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "tv_embedded", "mweb", "web"]
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

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
