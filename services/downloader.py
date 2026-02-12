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
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename
