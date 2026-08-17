import asyncio
import os
import re
import time
import yt_dlp
import aiohttp
import logging
import config  # ✅ Config import kiya gaya hai
from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, Playlist

# ----------------- CONFIGURATION -----------------
DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger(__name__)

# ✅ ShrutiBots API Setup
API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotskwvos7QCW6KasrmgpVtt")

def time_to_seconds(time_str):
    stringt = str(time_str)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

def get_safe_filename(title: str, default_id: str) -> str:
    """Removes invalid characters from titles to prevent OS file creation errors."""
    if not title:
        return default_id
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

# ----------------- DOWNLOADERS -----------------

# 🚀 1. FAST DOWNLOAD VIA SHRUTIBOTS API
async def api_download(video_id: str, download_type: str, title: str = None) -> str:
    if not API_URL or not API_KEY:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, video_id)
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={"url": video_id, "type": "audio" if download_type == "audio" else "video", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status != 200:
                    LOGGER.error(f"API Error: Status {resp.status}")
                    return None
                
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)
                        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        LOGGER.error(f"Shruti API Download Error: {e}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        return None

# 🛡️ 2. YOUTUBE YT-DLP FALLBACK
async def ytdl_fallback_download(link: str, download_type: str, title: str = None) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    filename = get_safe_filename(title, video_id)
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    video_format = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    
    ydl_opts = {
        'format': video_format if download_type == "video" else 'bestaudio/bestvideo+bestaudio/best', 
        'outtmpl': file_path,
        'quiet': True,
        'no_warnings': True,
        'cookiefile': 'cookies.txt', 
        'extractor_args': {'youtube': ['player_client=ios,tv_embedded']}, 
        'geo_bypass': True,
        'nocheckcertificate': True,
    }
    
    if download_type == "audio":
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([link]))
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        LOGGER.error(f"yt-dlp fallback error: {str(e)}")
        return None

# 🎵 3. SPOTIFY SOURCE-HOPPING
async def spotify_fallback_download(title: str) -> str:
    if not title: return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    clean_title = re.sub(r'\(.*?\)|\[.*?\]|official|video|audio|lyric', '', title, flags=re.IGNORECASE).strip()
    filename = get_safe_filename(clean_title, f"sp_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")

    try:
        async with aiohttp.ClientSession() as session:
            api_url = f"https://api.spotifydown.com/search?q={clean_title}" 
            
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get("success") and data.get("tracks"):
                        best_track_url = data["tracks"][0].get("downloadUrl") 
                        
                        if best_track_url:
                            async with session.get(best_track_url) as song_resp:
                                if song_resp.status == 200:
                                    with open(file_path, "wb") as f:
                                        async for chunk in song_resp.content.iter_chunked(131072):
                                            f.write(chunk)
                                            
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        LOGGER.info(f"🟢 SOURCE-HOPPING SUCCESS: Downloaded '{clean_title}' from Spotify!")
                                        return file_path
    except Exception as e:
        LOGGER.error(f"Spotify fallback error: {str(e)}")
    return None

# 🎵 4. JIOSAAVN SOURCE-HOPPING (✅ Fixed with config.JIOSAAVN_API)
async def jiosaavn_fallback_download(title: str) -> str:
    if not title: return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    clean_title = re.sub(r'\(.*?\)|\[.*?\]|official|video|audio|lyric', '', title, flags=re.IGNORECASE).strip()
    filename = get_safe_filename(clean_title, f"js_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")

    try:
        async with aiohttp.ClientSession() as session:
            # ✅ Using the API from config.py
            async with session.get(f"{config.JIOSAAVN_API}{clean_title}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("data", {}).get("results"):
                        song_data = data["data"]["results"][0]
                        download_urls = song_data.get("downloadUrl", [])
                        if download_urls:
                            best_url = download_urls[-1]["url"]
                            async with session.get(best_url) as song_resp:
                                if song_resp.status == 200:
                                    with open(file_path, "wb") as f:
                                        async for chunk in song_resp.content.iter_chunked(131072):
                                            f.write(chunk)
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        LOGGER.info(f"🟢 SOURCE-HOPPING SUCCESS: Downloaded '{clean_title}' from JioSaavn!")
                                        return file_path
    except Exception as e:
        LOGGER.error(f"JioSaavn fallback error: {str(e)}")
    return None

# 🎵 5. SOUNDCLOUD SOURCE-HOPPING
async def soundcloud_fallback_download(title: str) -> str:
    if not title: return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(r'\(.*?\)|\[.*?\]|official|video|audio|lyric', '', title, flags=re.IGNORECASE).strip()
    filename = get_safe_filename(clean_title, f"sc_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': file_path,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    }
    
    try:
        loop = asyncio.get_event_loop()
        search_query = f"scsearch1:{clean_title}"
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([search_query]))
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            LOGGER.info(f"🟢 SOURCE-HOPPING SUCCESS: Downloaded '{clean_title}' from SoundCloud!")
            return file_path
    except Exception as e:
        LOGGER.error(f"SoundCloud fallback error: {str(e)}")
    return None

# 🎧 MAIN AUDIO ENGINE
async def download_song(link: str, title: str = None) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None
        
    if not title:
        try:
            search = VideosSearch(video_id, limit=1)
            title = (await search.next())["result"][0]["title"]
        except Exception:
            pass

    # Phase 1: API
    api_result = await api_download(video_id, "audio", title)
    if api_result: return api_result
    
    # Phase 2: YouTube Fallback
    yt_result = await ytdl_fallback_download(link, "audio", title)
    if yt_result: return yt_result
    
    # Phase 3, 4 & 5: Source Hopping (Spotify -> JioSaavn -> SoundCloud)
    if title:
        LOGGER.warning(f"🔴 YouTube blocked '{title}'. Hopping to Spotify...")
        sp_result = await spotify_fallback_download(title)
        if sp_result: return sp_result

        LOGGER.warning(f"🔴 Spotify failed. Hopping to JioSaavn...")
        js_result = await jiosaavn_fallback_download(title)
        if js_result: return js_result

        LOGGER.warning(f"🔴 JioSaavn failed. Hopping to SoundCloud...")
        sc_result = await soundcloud_fallback_download(title)
        if sc_result: return sc_result

    return None

# 🎥 MAIN VIDEO ENGINE
async def download_video(link: str, title: str = None) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            search = VideosSearch(video_id, limit=1)
            title = (await search.next())["result"][0]["title"]
        except:
            pass

    api_result = await api_download(video_id, "video", title)
    if api_result: return api_result
    return await ytdl_fallback_download(link, "video", title)

# ----------------- YOUTUBE API CLASS -----------------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                for result in response["result"]:
                    title = result["title"]
                    duration_min = result["duration"]
                    thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                    vidid = result["id"]
                    duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
                    return title, duration_min, duration_sec, thumbnail, vidid
        except Exception:
            pass

        try:
            loop = asyncio.get_event_loop()
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "cookiefile": "cookies.txt",
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            } 
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            
            r = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                title = entry.get("title")
                vidid = entry.get("id")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)
                duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                thumbnail = f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg"
                return title, duration_min, dur_sec, thumbnail, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in details: {e}")

        return None, None, None, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["title"]
        except Exception:
            return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["duration"]
        except Exception:
            return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["thumbnails"][0]["url"].split("?")[0]
        except Exception:
            return "https://telegra.ph/file/2e3d368e77c449c287430.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                result = response["result"][0]
                title = result["title"]
                duration_min = result["duration"]
                vidid = result["id"]
                yturl = result["link"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                return {
                    "title": title,
                    "link": yturl,
                    "vidid": vidid,
                    "duration_min": duration_min,
                    "thumb": thumbnail,
                }, vidid
        except Exception:
            pass

        try:
            loop = asyncio.get_event_loop()
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "cookiefile": "cookies.txt",
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            }
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            r = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
            
            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                vidid = entry.get("id")
                title = entry.get("title")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)
                duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                thumbnail = f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg"
                
                return {
                    "title": title,
                    "link": f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": duration_min,
                    "thumb": thumbnail,
                }, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in track: {e}")

        return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        ytdl_opts = {
            "quiet": True,
            "cookiefile": "cookies.txt", 
            "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "-x", "16",            
                "-s", "16",            
                "-k", "1M",            
                "--allow-piece-length-change=true"
            ]
        }
        
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        formats_available = []
        loop = asyncio.get_event_loop()
        
        try:
            r = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=False))
            if r and "formats" in r:
                for format in r["formats"]:
                    try:
                        if "dash" not in str(format.get("format", "")).lower():
                            formats_available.append(
                                {
                                    "format": format.get("format"),
                                    "filesize": format.get("filesize"),
                                    "format_id": format.get("format_id"),
                                    "ext": format.get("ext"),
                                    "format_note": format.get("format_note"),
                                    "yturl": link,
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            pass
            
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
            
        try:
            a = VideosSearch(link, limit=10)
            result = (await a.next()).get("result")
            title = result[query_type]["title"]
            duration_min = result[query_type]["duration"]
            vidid = result[query_type]["id"]
            thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
            return title, duration_min, thumbnail, vidid
        except Exception:
            return "Unknown Title", "0:00", "https://telegra.ph/file/2e3d368e77c449c287430.jpg", "None"

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        try:
            file_title = title if isinstance(title, str) else None

            if video:
                downloaded_file = await download_video(link, title=file_title)
            else:
                downloaded_file = await download_song(link, title=file_title)
                
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception as e:
            LOGGER.error(f"Error in YouTubeAPI.download: {e}")
            return None, False

    async def autoplay(self, last_vidid: str, title: str, max_duration: int = None):
        try:
            import random
            search_query = f"{title} official audio"
            valid_choices = []
            
            try:
                search = VideosSearch(search_query, limit=15)
                result = await search.next()
                if result and result.get("result"):
                    for res in result["result"]:
                        vidid = str(res.get("id") or "")
                        if not vidid or vidid == "None" or vidid == last_vidid:
                            continue
                            
                        dur_str = str(res.get("duration", "0:00"))
                        dur_sec = 0
                        if dur_str and ":" in dur_str:
                            parts = dur_str.split(":")
                            try:
                                if len(parts) == 2:
                                    dur_sec = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3:
                                    dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except ValueError:
                                pass
                                
                        if dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue
                            
                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(res.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })
            except Exception:
                pass 

            if not valid_choices:
                loop = asyncio.get_event_loop()
                ytdl_opts = {
                    "quiet": True, 
                    "extract_flat": True, 
                    "cookiefile": "cookies.txt",
                    "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
                } 
                ydl = yt_dlp.YoutubeDL(ytdl_opts)
                
                r = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch10:{search_query}", download=False))
                if r and "entries" in r:
                    for entry in r["entries"]:
                        vidid = entry.get("id")
                        if not vidid or vidid == last_vidid:
                            continue
                        
                        raw_dur = entry.get("duration", 0)
                        try:
                            dur_sec = int(float(raw_dur)) if raw_dur else 0
                        except (ValueError, TypeError):
                            dur_sec = 0
                            
                        if not dur_sec or dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue
                            
                        m, s = divmod(dur_sec, 60)
                        h, m = divmod(m, 60)
                        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                        
                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(entry.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })

            if valid_choices:
                return random.choice(valid_choices)
                
            return None
            
        except Exception as e:
            LOGGER.error(f"YouTube Autoplay Function Error: {e}")
            return None

YouTube = YouTubeAPI()
