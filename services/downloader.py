import yt_dlp
import os
import uuid

def download_instagram_video(url: str, output_dir: str = "temp") -> tuple[str, dict]:
    """
    Downloads an Instagram video using yt-dlp and returns the path to the file and metadata.
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
            
            # Extract relevant metadata
            # For Instagram, uploader_id is often the handle, but sometimes numeric ID.
            # uploader is often the full name.
            # channel is sometimes the handle.
            
            author_name = info.get("uploader_id")
            
            # Check if author_name is valid (not purely numeric)
            if not author_name or (author_name.isdigit()):
                # Try channel
                if info.get("channel") and not info.get("channel").isdigit():
                    author_name = info.get("channel")
                
                # Try extracting from title (e.g. "Video by appetitnotv")
                if not author_name:
                    title = info.get("title", "")
                    import re
                    # Match "Video by username" or similar patterns if they exist
                    # Based on user report: "Video by appetitnotv"
                    match = re.search(r'Video by ([^\s]+)', title)
                    if match:
                        author_name = match.group(1)

            # LAST RESORT: Extract from URL (e.g. instagram.com/username/reel/...)
            # Note: The input URL might be shortened or different, but info['webpage_url'] should be canonical
            if not author_name or author_name.isdigit():
                import re
                webpage_url = info.get("webpage_url", url)
                match = re.search(r'instagram\.com/([^/?#]+)', webpage_url)
                if match:
                    potential_handle = match.group(1)
                    if potential_handle not in ['reel', 'p', 'stories', 'explore']:
                        author_name = potential_handle

            metadata = {
                "author_name": author_name or info.get("uploader") or "Unknown Chef",
                "title": info.get("title"),
                "description": info.get("description")
            }
            
            return filename, metadata
    except yt_dlp.utils.DownloadError as e:
        raise ValueError(f"Failed to download video: {str(e)}")
    except Exception as e:
        raise ValueError(f"An unexpected error occurred during download: {str(e)}")
