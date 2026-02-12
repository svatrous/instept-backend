import yt_dlp
import os
import uuid

def download_instagram_video(url: str, output_dir: str = "temp") -> str:
    """
    Downloads an Instagram video using yt-dlp and returns the path to the file.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate a unique filename to avoid collisions
    file_id = str(uuid.uuid4())
    output_template = os.path.join(output_dir, f"{file_id}.%(ext)s")

    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best',
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except yt_dlp.utils.DownloadError as e:
        raise ValueError(f"Failed to download video: {str(e)}")
    except Exception as e:
        raise ValueError(f"An unexpected error occurred during download: {str(e)}")
