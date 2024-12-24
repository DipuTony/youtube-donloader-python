from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
from pathlib import Path
import yt_dlp  # for video and metadata extraction

app = FastAPI()

# Define request model
class MediaRequest(BaseModel):
    videoUrl: str
    format: str = "bestaudio/best"  # default format is best audio

# Define video metadata response model
class VideoMetadata(BaseModel):
    title: str
    author: str
    length_seconds: int
    view_count: int
    upload_date: str
    likes: int
    description: str
    thumbnails: list

# Base directory for downloads
BASE_DOWNLOAD_DIR = Path("./downloads")
BASE_DOWNLOAD_DIR.mkdir(exist_ok=True)

# ffmpeg and yt-dlp paths (use system-installed versions)
FFMPEG_PATH = "ffmpeg"  # Ensure ffmpeg is in your PATH
YT_DLP_PATH = "yt-dlp"  # Ensure yt-dlp is installed globally or in your venv

def download_media(video_url: str, media_format: str, output_file: Path) -> None:
    """
    Downloads media using yt-dlp and converts it to the specified format using ffmpeg.
    """
    command = [
        YT_DLP_PATH,
        video_url,
        "--format", media_format,
        "-o", "-",  # Stream output to stdout
    ]
    ffmpeg_command = [
        FFMPEG_PATH,
        "-i", "pipe:0",  # Read from stdin (yt-dlp output)
        "-vn",  # No video
        "-acodec", "libmp3lame",  # Use MP3 codec
        "-ar", "44100",  # Audio sampling rate
        "-ab", "192k",  # Audio bitrate
        "-f", "mp3",  # Output format
        str(output_file),
    ]

    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE) as yt_dlp_proc:
            with subprocess.Popen(ffmpeg_command, stdin=yt_dlp_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as ffmpeg_proc:
                ffmpeg_stdout, ffmpeg_stderr = ffmpeg_proc.communicate()
                if ffmpeg_proc.returncode != 0:
                    raise Exception(f"FFmpeg error: {ffmpeg_stderr.decode('utf-8')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")


@app.get("/api/youtube-video-details", response_model=VideoMetadata)
async def youtube_metadata(video: MediaRequest):
    """
    Fetches metadata for a YouTube video.
    """
    video_url = video.videoUrl
    if not video_url:
        raise HTTPException(status_code=400, detail="Video URL is required.")

    try:
        # Fetch video metadata using yt-dlp
        ydl_opts = {
            'quiet': True,
            'force_generic_extractor': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_info = ydl.extract_info(video_url, download=False)

        metadata = VideoMetadata(
            title=video_info['title'],
            author=video_info['uploader'],
            length_seconds=video_info['duration'],
            view_count=video_info.get('view_count', 0),
            upload_date=video_info['upload_date'],
            likes=video_info.get('like_count', 0),
            description=video_info.get('description', ''),
            thumbnails=video_info['thumbnails']
        )
        return metadata

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching video details: {str(e)}")


@app.post("/api/youtube-to-mp3")
async def youtube_to_mp3(request: MediaRequest):
    """
    Converts YouTube video to MP3 and sends it as a downloadable response.
    """
    video_url = request.videoUrl
    media_format = request.format

    if not video_url:
        raise HTTPException(status_code=400, detail="Video URL is required.")

    output_file = BASE_DOWNLOAD_DIR / "audio.mp3"

    try:
        # Download and convert video to MP3
        download_media(video_url, media_format, output_file)

        if not output_file.exists():
            raise HTTPException(status_code=500, detail="Audio conversion failed, file not created.")

        # Send the MP3 file as a response
        return FileResponse(
            output_file,
            media_type="audio/mpeg",
            filename="audio.mp3",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing the request: {str(e)}")
    finally:
        # Clean up: Delete the file after sending
        if output_file.exists():
            output_file.unlink()


@app.post("/api/youtube-to-video")
async def youtube_to_video(request: MediaRequest):
    """
    Downloads YouTube video in the requested format and sends it as a downloadable response.
    """
    video_url = request.videoUrl
    media_format = request.format

    if not video_url:
        raise HTTPException(status_code=400, detail="Video URL is required.")

    output_file = BASE_DOWNLOAD_DIR / "video.mp4"

    try:
        # Use yt-dlp to download the video
        command = [
            YT_DLP_PATH,
            video_url,
            "--format", media_format,
            "-o", str(output_file),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"yt-dlp error: {result.stderr}")

        if not output_file.exists():
            raise HTTPException(status_code=500, detail="Video download failed, file not created.")

        # Send the video file as a response
        return FileResponse(
            output_file,
            media_type="video/mp4",
            filename="video.mp4",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing the request: {str(e)}")
    finally:
        # Clean up: Delete the file after sending
        if output_file.exists():
            output_file.unlink()
