import streamlit as st
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs
import subprocess
import re
import glob
import os
import json
import requests
import pandas as pd
import time

# ------------------------------
# KONFIGURASI API YOUTUBE
# ------------------------------
# Ganti API_KEY dengan milikmu sendiri
API_KEY = "AIzaSyDMswyIKiMuKQw074P3h2SmPSjg9yYByj0"
youtube = build("youtube", "v3", developerKey=API_KEY)

# ------------------------------
# UTILITAS
# ------------------------------
def extract_video_id(url):
    try:
        parsed_url = urlparse(url.strip())
        if parsed_url.hostname in ["www.youtube.com", "youtube.com"]:
            return parse_qs(parsed_url.query).get("v", [None])[0]
        elif parsed_url.hostname == "youtu.be":
            return parsed_url.path.lstrip("/")
        return None
    except Exception:
        return None


def clean_html_tags(text):
    if not text:
        return ""
    clean = re.sub(r"<[^>]*>", "", text)
    return clean.strip()


def get_video_details(video_id):
    try:
        request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id
        )
        response = request.execute()
        if not response.get("items"):
            return None
        return response["items"][0]
    except Exception as e:
        st.error(f"Gagal mengambil data video: {e}")
        return None


def get_dislike_count(video_id):
    """Ambil dislike count dari ReturnYouTubeDislike API"""
    try:
        url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("dislikes", "Data tidak tersedia")
        else:
            return "Data tidak tersedia"
    except Exception:
        return "Data tidak tersedia"


def get_comments(video_id, max_results=20):
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_results,
            order="relevance"
        )
        response = request.execute()
        comments = []
        if "items" in response:
            for item in response["items"]:
                comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                comments.append(clean_html_tags(comment))
        return comments
    except Exception:
        return ["Komentar tidak tersedia"]


def download_transcript(video_url):
    try:
        title = subprocess.check_output(
            ["yt-dlp", "--get-title", video_url],
            text=True
        ).strip()
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)

        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-subs",
                "--sub-lang", "id",
                "--skip-download",
                "--convert-subs", "srt",
                video_url,
                "-o", f"{safe_title}.%(ext)s"
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return "Transkrip tidak tersedia"

        sub_files = glob.glob(f"{safe_title}*.srt")
        if not sub_files:
            return "Transkrip tidak tersedia"

        sub_filename = sub_files[0]

        with open(sub_filename, "r", encoding="utf-8") as f:
            data = f.read()

        lines = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> .*", "", data)
        lines = re.sub(r"\n+", "\n", lines).strip().split("\n")

        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and (not cleaned_lines or line != cleaned_lines[-1]):
                cleaned_lines.append(line)

        os.remove(sub_filename)

        return " ".join(cleaned_lines)
    except Exception:
        return "Transkrip tidak tersedia"


def duration_to_seconds(duration):
    """Konversi durasi ISO 8601 ke total detik"""
    try:
        hours = minutes = seconds = 0
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if match:
            hours = int(match.group(1)) if match.group(1) else 0
            minutes = int(match.group(2)) if match.group(2) else 0
            seconds = int(match.group(3)) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return "Data tidak tersedia"


# ------------------------------
# STREAMLIT APP
# ------------------------------
st.set_page_config(page_title="YouTube Data Viewer", layout="wide")
st.title("📊 YouTube Data Viewer (Multi-link dengan Progress Bar)")

youtube_links = st.text_area(
    "Masukkan satu atau beberapa link YouTube (pisahkan dengan koma):",
    placeholder="contoh: https://www.youtube.com/watch?v=abc123, https://youtu.be/xyz456"
)

if st.button("Ambil Data"):
    if not youtube_links.strip():
        st.warning("⚠️ Silakan masukkan minimal satu link YouTube terlebih dahulu.")
    else:
        links = [link.strip() for link in youtube_links.split(",") if link.strip()]
        data_rows = []

        progress = st.progress(0)
        status_text = st.empty()

        for idx, link in enumerate(links):
            status_text.text(f"⏳ Mengambil data untuk video {idx+1}/{len(links)}...")
            video_id = extract_video_id(link)

            if not video_id:
                st.error(f"❌ Link tidak valid: {link}")
                continue

            video_data = get_video_details(video_id)
            if not video_data:
                st.warning(f"⚠️ Data tidak ditemukan untuk video: {link}")
                continue

            snippet = video_data.get("snippet", {})
            stats = video_data.get("statistics", {})
            content = video_data.get("contentDetails", {})

            title = snippet.get("title", "Data tidak tersedia")
            tags = ", ".join(snippet.get("tags", [])) if snippet.get("tags") else "Data tidak tersedia"
            description = clean_html_tags(snippet.get("description", "Data tidak tersedia"))
            views = stats.get("viewCount", "Data tidak tersedia")
            likes = stats.get("likeCount", "Data tidak tersedia")
            comments_count = stats.get("commentCount", "Data tidak tersedia")
            duration_seconds = duration_to_seconds(content.get("duration", ""))

            # Ambil dislike, komentar, dan transkrip
            dislikes = get_dislike_count(video_id)
            comments = get_comments(video_id, 20)
            comments_joined = "\n".join(comments)
            transcript = download_transcript(link)

            row = {
                "Link YT": link,
                "Tags": tags,
                "Title": title,
                "Likes": likes,
                "Dislike": dislikes,
                "Views": views,
                "Comments count": comments_count,
                "Comments (Top 20)": comments_joined,
                "Duration": f"{duration_seconds} detik" if isinstance(duration_seconds, int) else "Data tidak tersedia",
                "Video description": description,
                "Transkrip": transcript
            }

            data_rows.append(row)
            progress.progress((idx + 1) / len(links))
            time.sleep(0.2)

        status_text.text("✅ Semua data berhasil diambil!")

        if data_rows:
            df = pd.DataFrame(data_rows)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Tidak ada data video yang berhasil diambil.")
