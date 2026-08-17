import asyncio
import logging
import os
import re
import time
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.future import Playlist, VideosSearch

import config


# ----------------- CONFIGURATION -----------------

DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger(__name__)

API_URL = os.environ.get(
    "SHRUTI_API_URL",
    "https://api.shrutibots.site",
)

API_KEY = os.environ.get(
    "SHRUTI_API_KEY",
    "ShrutiBotsmKSBhBaGhKcXoYLNDLMX",
)

# Worker API
WORKER_FALLBACK_API_URL = os.getenv(
    "WORKER_FALLBACK_API_URL",
    "https://youtubenewapi.skybotsdeveloper.workers.dev",
)

WORKER_FALLBACK_API_KEY = os.getenv(
    "WORKER_FALLBACK_API_KEY",
    "itsmesid",
)


# ----------------- HELPERS -----------------

def time_to_seconds(time_str):
    stringt = str(time_str)
    return sum(
        int(x) * 60 ** i
        for i, x in enumerate(reversed(stringt.split(":")))
    )


def get_safe_filename(title: str, default_id: str) -> str:
    if not title:
        return default_id

    return re.sub(
        r'[\\/*?:"<>|]',
        "",
        title,
    ).strip()


def extract_video_id(link: str) -> str:
    """
    Extract YouTube video ID from common URL formats.
    """

    if not link:
        return ""

    link = str(link).strip()

    if "youtu.be/" in link:
        return link.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0]

    if "v=" in link:
        return link.split("v=", 1)[1].split("&", 1)[0]

    if "/shorts/" in link:
        return link.split("/shorts/", 1)[1].split("?", 1)[0].split("&", 1)[0]

    if "/embed/" in link:
        return link.split("/embed/", 1)[1].split("?", 1)[0].split("&", 1)[0]

    return link


async def _async_run(func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    return await loop.run_in_executor(
        None,
        lambda: func(*args, **kwargs),
    )


# ----------------- DOWNLOADERS -----------------

async def api_download(
    video_id: str,
    download_type: str,
    title: str = None,
) -> str:

    if not API_URL or not API_KEY:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    filename = get_safe_filename(
        title,
        video_id,
    )

    ext = "mp4" if download_type == "video" else "mp3"

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.{ext}",
    )

    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 50000
    ):
        return file_path

    try:
        generous_timeout = aiohttp.ClientTimeout(
            total=600,
            sock_connect=10,
            sock_read=15,
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={
                    "url": video_id,
                    "type": (
                        "audio"
                        if download_type == "audio"
                        else "video"
                    ),
                    "api_key": API_KEY,
                },
                timeout=generous_timeout,
            ) as resp:

                if resp.status != 200:
                    LOGGER.error(
                        f"Shruti API Error: Status {resp.status}"
                    )
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 50000
        ):
            LOGGER.info(
                f"Downloaded '{title}' from Shruti API!"
            )
            return file_path

        LOGGER.warning(
            f"Shruti API returned corrupted/empty file for '{title}'."
        )

        return None

    except asyncio.TimeoutError:
        LOGGER.warning("Shruti API Timeout!")

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return None

    except Exception as e:
        LOGGER.error(
            f"Shruti API Download Error: {e}"
        )

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return None


# ----------------- WORKER DOWNLOADER -----------------

async def worker_api_download(
    video_id: str,
    download_type: str,
    title: str = None,
) -> str:

    if (
        not WORKER_FALLBACK_API_URL
        or not WORKER_FALLBACK_API_KEY
    ):
        return None

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    filename = get_safe_filename(
        title,
        f"wk_{video_id}",
    )

    ext = "mp4" if download_type == "video" else "mp3"

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.{ext}",
    )

    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 50000
    ):
        return file_path

    try:
        fast_timeout = aiohttp.ClientTimeout(
            total=120,
            sock_connect=3.0,
            sock_read=4.0,
        )

        async with aiohttp.ClientSession() as session:

            params = {
                "url": video_id,
                "type": (
                    "audio"
                    if download_type == "audio"
                    else "video"
                ),
                "api_key": WORKER_FALLBACK_API_KEY,
            }

            async with session.get(
                f"{WORKER_FALLBACK_API_URL}/download",
                params=params,
                timeout=fast_timeout,
            ) as resp:

                if resp.status != 200:
                    LOGGER.error(
                        f"Worker API Error: Status {resp.status}"
                    )
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 50000
        ):
            LOGGER.info(
                f"Downloaded '{title}' from Worker API!"
            )
            return file_path

        LOGGER.warning(
            f"Worker API returned corrupted/empty file for '{title}'."
        )

        return None

    except asyncio.TimeoutError:
        LOGGER.warning(
            "Worker API Timeout! Moving to next fallback."
        )

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return None

    except Exception as e:
        LOGGER.error(
            f"Worker API Download Error: {e}"
        )

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        return None


# ----------------- YT-DLP FALLBACK -----------------

async def ytdl_fallback_download(
    link: str,
    download_type: str,
    title: str = None,
) -> str:

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    video_id = extract_video_id(link)

    filename = get_safe_filename(
        title,
        video_id,
    )

    ext = "mp4" if download_type == "video" else "mp3"

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.{ext}",
    )

    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 50000
    ):
        return file_path

    video_format = (
        "bestvideo[height<=720][ext=mp4]"
        "+bestaudio[ext=m4a]/"
        "best[ext=mp4]/best"
    )

    ydl_opts = {
        "format": (
            video_format
            if download_type == "video"
            else "bestaudio/best"
        ),
        "outtmpl": file_path,
        "quiet": True,
        "no_warnings": True,
        "cookiefile": "cookies.txt",
        "extractor_args": {
            "youtube": [
                "player_client=ios,tv_embedded"
            ]
        },
        "geo_bypass": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }

    if download_type == "audio":
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    try:
        await _async_run(
            yt_dlp.YoutubeDL(ydl_opts).download,
            [link],
        )

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 50000
        ):
            LOGGER.info(
                f"Downloaded '{title}' from yt-dlp!"
            )
            return file_path

        return None

    except Exception as e:
        LOGGER.error(
            f"yt-dlp fallback error: {e}"
        )
        return None


# ----------------- SPOTIFY FALLBACK -----------------

async def spotify_fallback_download(
    title: str,
) -> str:

    if not title:
        return None

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    filename = get_safe_filename(
        clean_title,
        f"sp_{int(time.time())}",
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.mp3",
    )

    try:
        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            api_url = (
                "https://api.spotifydown.com/search"
                f"?q={clean_title}"
            )

            async with session.get(api_url) as resp:

                if resp.status != 200:
                    return None

                data = await resp.json()

                if (
                    data.get("success")
                    and data.get("tracks")
                ):
                    best_track_url = (
                        data["tracks"][0].get(
                            "downloadUrl"
                        )
                    )

                    if best_track_url:

                        async with session.get(
                            best_track_url
                        ) as song_resp:

                            if song_resp.status == 200:

                                with open(
                                    file_path,
                                    "wb",
                                ) as f:

                                    async for chunk in song_resp.content.iter_chunked(
                                        131072
                                    ):
                                        f.write(chunk)

                                if (
                                    os.path.exists(file_path)
                                    and os.path.getsize(file_path)
                                    > 50000
                                ):
                                    LOGGER.info(
                                        f"Downloaded '{clean_title}' from Spotify!"
                                    )
                                    return file_path

    except Exception as e:
        LOGGER.error(
            f"Spotify fallback error: {e}"
        )

    return None


# ----------------- JIOSAAVN FALLBACK -----------------

async def jiosaavn_fallback_download(
    title: str,
) -> str:

    if not title:
        return None

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    filename = get_safe_filename(
        clean_title,
        f"js_{int(time.time())}",
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.mp3",
    )

    try:
        api_base = getattr(
            config,
            "JIOSAAVN_API",
            "https://saavn.dev/api/search/songs?query=",
        )

        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                f"{api_base}{clean_title}"
            ) as resp:

                if resp.status != 200:
                    return None

                data = await resp.json()

                results = (
                    data.get("data", {})
                    .get("results", [])
                )

                if (
                    data.get("success")
                    and results
                ):

                    song_data = results[0]

                    download_urls = song_data.get(
                        "downloadUrl",
                        [],
                    )

                    if download_urls:

                        best_url = download_urls[-1].get(
                            "url"
                        )

                        if best_url:

                            async with session.get(
                                best_url
                            ) as song_resp:

                                if song_resp.status == 200:

                                    with open(
                                        file_path,
                                        "wb",
                                    ) as f:

                                        async for chunk in song_resp.content.iter_chunked(
                                            131072
                                        ):
                                            f.write(chunk)

                                    if (
                                        os.path.exists(file_path)
                                        and os.path.getsize(file_path)
                                        > 50000
                                    ):
                                        LOGGER.info(
                                            f"Downloaded '{clean_title}' from JioSaavn!"
                                        )
                                        return file_path

    except Exception as e:
        LOGGER.error(
            f"JioSaavn fallback error: {e}"
        )

    return None


# ----------------- SOUNDCLOUD FALLBACK -----------------

async def soundcloud_fallback_download(
    title: str,
) -> str:

    if not title:
        return None

    os.makedirs(
        DOWNLOAD_DIR,
        exist_ok=True,
    )

    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    filename = get_safe_filename(
        clean_title,
        f"sc_{int(time.time())}",
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{filename}.mp3",
    )

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": file_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        search_query = (
            f"scsearch1:{clean_title}"
        )

        await _async_run(
            yt_dlp.YoutubeDL(ydl_opts).download,
            [search_query],
        )

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 50000
        ):
            LOGGER.info(
                f"Downloaded '{clean_title}' from SoundCloud!"
            )
            return file_path

    except Exception as e:
        LOGGER.error(
            f"SoundCloud fallback error: {e}"
        )

    return None


# ----------------- MAIN DOWNLOAD SONG -----------------

async def download_song(
    link: str,
    title: str = None,
) -> str:

    video_id = extract_video_id(link)

    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            search = VideosSearch(
                video_id,
                limit=1,
            )

            res = await search.next()

            if res and res.get("result"):
                title = res["result"][0]["title"]

        except Exception:
            pass

    # 1. Worker API
    worker_result = await worker_api_download(
        video_id,
        "audio",
        title,
    )

    if worker_result:
        return worker_result

    LOGGER.warning(
        f"Worker API failed for '{title}'. "
        "Trying Shruti API..."
    )

    # 2. Shruti API
    api_result = await api_download(
        video_id,
        "audio",
        title,
    )

    if api_result:
        return api_result

    LOGGER.warning(
        f"Shruti API failed for '{title}'. "
        "Trying yt-dlp..."
    )

    # 3. yt-dlp
    yt_result = await ytdl_fallback_download(
        link,
        "audio",
        title,
    )

    if yt_result:
        return yt_result

    if title:

        LOGGER.warning(
            f"YouTube download failed for '{title}'. "
            "Trying Spotify..."
        )

        # 4. Spotify
        sp_result = await spotify_fallback_download(
            title
        )

        if sp_result:
            return sp_result

        LOGGER.warning(
            "Spotify failed. Trying JioSaavn..."
        )

        # 5. JioSaavn
        js_result = await jiosaavn_fallback_download(
            title
        )

        if js_result:
            return js_result

        LOGGER.warning(
            "JioSaavn failed. Trying SoundCloud..."
        )

        # 6. SoundCloud
        sc_result = await soundcloud_fallback_download(
            title
        )

        if sc_result:
            return sc_result

    return None


# ----------------- MAIN DOWNLOAD VIDEO -----------------

async def download_video(
    link: str,
    title: str = None,
) -> str:

    video_id = extract_video_id(link)

    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            search = VideosSearch(
                video_id,
                limit=1,
            )

            res = await search.next()

            if res and res.get("result"):
                title = res["result"][0]["title"]

        except Exception:
            pass

    # 1. Worker API
    worker_result = await worker_api_download(
        video_id,
        "video",
        title,
    )

    if worker_result:
        return worker_result

    LOGGER.warning(
        f"Worker API failed for '{title}'. "
        "Trying Shruti API..."
    )

    # 2. Shruti API
    api_result = await api_download(
        video_id,
        "video",
        title,
    )

    if api_result:
        return api_result

    LOGGER.warning(
        f"Shruti API failed for '{title}'. "
        "Trying yt-dlp..."
    )

    # 3. yt-dlp
    return await ytdl_fallback_download(
        link,
        "video",
        title,
    )


# ----------------- YOUTUBE API CLASS -----------------

class YouTubeAPI:

    def __init__(self):
        self.base = (
            "https://www.youtube.com/watch?v="
        )

        self.regex = r"(?:youtube\.com|youtu\.be)"

        self.status = (
            "https://www.youtube.com/oembed?url="
        )

        self.listbase = (
            "https://youtube.com/playlist?list="
        )

        self.reg = re.compile(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )

    # ----------------- EXISTS -----------------

    async def exists(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        return bool(
            re.search(
                self.regex,
                link,
            )
        )

    # ----------------- URL -----------------

    async def url(
        self,
        message_1: Message,
    ) -> Union[str, None]:

        messages = [message_1]

        if message_1.reply_to_message:
            messages.append(
                message_1.reply_to_message
            )

        for message in messages:

            if message.entities:

                for entity in message.entities:

                    if entity.type == MessageEntityType.URL:

                        text = (
                            message.text
                            or message.caption
                            or ""
                        )

                        return text[
                            entity.offset:
                            entity.offset + entity.length
                        ]

                    if (
                        entity.type
                        == MessageEntityType.TEXT_LINK
                    ):
                        return entity.url

            if message.caption_entities:

                for entity in message.caption_entities:

                    if (
                        entity.type
                        == MessageEntityType.TEXT_LINK
                    ):
                        return entity.url

        return None

    # ----------------- DETAILS -----------------

    async def details(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:
            results = VideosSearch(
                link,
                limit=1,
            )

            response = await results.next()

            if response and response.get("result"):

                result = response["result"][0]

                title = result["title"]
                duration_min = result["duration"]

                thumbnail = (
                    result["thumbnails"][0]["url"]
                    .split("?")[0]
                )

                vidid = result["id"]

                duration_sec = (
                    int(time_to_seconds(duration_min))
                    if duration_min
                    else 0
                )

                return (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                )

        except Exception:
            pass

        # yt-dlp fallback
        try:

            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "cookiefile": "cookies.txt",
                "extractor_args": {
                    "youtube": [
                        "player_client=ios,tv_embedded"
                    ]
                },
            }

            ydl = yt_dlp.YoutubeDL(
                ydl_opts
            )

            search_query = (
                link
                if (
                    "youtube.com" in link
                    or "youtu.be" in link
                )
                else f"ytsearch1:{link}"
            )

            r = await _async_run(
                ydl.extract_info,
                search_query,
                download=False,
            )

            entries = (
                r.get("entries", [])
                if r
                else []
            )

            if entries:

                entry = entries[0]

                title = entry.get("title")
                vidid = entry.get("id")

                dur_sec = int(
                    entry.get("duration", 0)
                    or 0
                )

                m, s = divmod(
                    dur_sec,
                    60,
                )

                h, m = divmod(
                    m,
                    60,
                )

                duration_min = (
                    f"{h}:{m:02d}:{s:02d}"
                    if h
                    else f"{m}:{s:02d}"
                )

                thumbnail = (
                    f"https://img.youtube.com/vi/"
                    f"{vidid}/hqdefault.jpg"
                )

                return (
                    title,
                    duration_min,
                    dur_sec,
                    thumbnail,
                    vidid,
                )

        except Exception as e:

            LOGGER.error(
                f"yt-dlp search fallback failed "
                f"in details: {e}"
            )

        return (
            None,
            None,
            None,
            None,
            None,
        )

    # ----------------- TITLE -----------------

    async def title(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:
            results = VideosSearch(
                link,
                limit=1,
            )

            response = await results.next()

            if response and response.get("result"):
                return response["result"][0]["title"]

        except Exception:
            pass

        return "Unknown Title"

    # ----------------- DURATION -----------------

    async def duration(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:
            results = VideosSearch(
                link,
                limit=1,
            )

            response = await results.next()

            if response and response.get("result"):
                return response["result"][0]["duration"]

        except Exception:
            pass

        return "0:00"

    # ----------------- THUMBNAIL -----------------

    async def thumbnail(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:
            results = VideosSearch(
                link,
                limit=1,
            )

            response = await results.next()

            if response and response.get("result"):
                return (
                    response["result"][0]["thumbnails"][0]["url"]
                    .split("?")[0]
                )

        except Exception:
            pass

        return (
            "https://telegra.ph/file/"
            "2e3d368e77c449c287430.jpg"
        )

    # ----------------- VIDEO -----------------

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:

            downloaded_file = await download_video(
                link
            )

            if downloaded_file:
                return 1, downloaded_file

            return (
                0,
                "Video download failed",
            )

        except Exception as e:

            return (
                0,
                f"Video download error: {e}",
            )

    # ----------------- PLAYLIST -----------------

    async def playlist(
        self,
        link,
        limit,
        user_id,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.listbase + link

        if "&" in link:
            link = link.split("&")[0]

        try:
            plist = await _async_run(
                Playlist.get,
                link,
            )

        except Exception:
            return []

        videos = plist.get(
            "videos"
        ) or []

        ids = []

        for data in videos[:limit]:

            if not data:
                continue

            vid = data.get("id")

            if not vid:
                continue

            ids.append(vid)

        return ids

    # ----------------- TRACK -----------------

    async def track(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:

            results = VideosSearch(
                link,
                limit=1,
            )

            response = await results.next()

            if response and response.get("result"):

                result = response["result"][0]

                return {
                    "title": result["title"],
                    "link": result["link"],
                    "vidid": result["id"],
                    "duration_min": result["duration"],
                    "thumb": (
                        result["thumbnails"][0]["url"]
                        .split("?")[0]
                    ),
                }, result["id"]

        except Exception:
            pass

        # yt-dlp fallback
        try:

            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "cookiefile": "cookies.txt",
                "extractor_args": {
                    "youtube": [
                        "player_client=ios,tv_embedded"
                    ]
                },
            }

            ydl = yt_dlp.YoutubeDL(
                ydl_opts
            )

            search_query = (
                link
                if (
                    "youtube.com" in link
                    or "youtu.be" in link
                )
                else f"ytsearch1:{link}"
            )

            r = await _async_run(
                ydl.extract_info,
                search_query,
                download=False,
            )

            entries = (
                r.get("entries", [])
                if r
                else []
            )

            if entries:

                entry = entries[0]

                vidid = entry.get("id")

                dur_sec = int(
                    entry.get("duration", 0)
                    or 0
                )

                m, s = divmod(
                    dur_sec,
                    60,
                )

                h, m = divmod(
                    m,
                    60,
                )

                duration_min = (
                    f"{h}:{m:02d}:{s:02d}"
                    if h
                    else f"{m}:{s:02d}"
                )

                return {
                    "title": entry.get(
                        "title"
                    ),
                    "link": (
                        f"https://www.youtube.com/watch?v="
                        f"{vidid}"
                    ),
                    "vidid": vidid,
                    "duration_min": duration_min,
                    "thumb": (
                        f"https://img.youtube.com/vi/"
                        f"{vidid}/hqdefault.jpg"
                    ),
                }, vidid

        except Exception as e:

            LOGGER.error(
                f"yt-dlp search fallback failed "
                f"in track: {e}"
            )

        return None, None

    # ----------------- FORMATS -----------------

    async def formats(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        ytdl_opts = {
            "quiet": True,
            "cookiefile": "cookies.txt",
            "extractor_args": {
                "youtube": [
                    "player_client=ios,tv_embedded"
                ]
            },
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "-x",
                "16",
                "-s",
                "16",
                "-k",
                "1M",
                "--allow-piece-length-change=true",
            ],
        }

        ydl = yt_dlp.YoutubeDL(
            ytdl_opts
        )

        formats_available = []

        try:

            r = await _async_run(
                ydl.extract_info,
                link,
                download=False,
            )

            if r and "formats" in r:

                for fmt in r["formats"]:

                    try:

                        if (
                            "dash"
                            not in str(
                                fmt.get(
                                    "format",
                                    "",
                                )
                            ).lower()
                        ):

                            formats_available.append(
                                {
                                    "format": fmt.get(
                                        "format"
                                    ),
                                    "filesize": fmt.get(
                                        "filesize"
                                    ),
                                    "format_id": fmt.get(
                                        "format_id"
                                    ),
                                    "ext": fmt.get(
                                        "ext"
                                    ),
                                    "format_note": fmt.get(
                                        "format_note"
                                    ),
                                    "yturl": link,
                                }
                            )

                    except Exception:
                        continue

        except Exception:
            pass

        return (
            formats_available,
            link,
        )

    # ----------------- SLIDER -----------------

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + link

        if "&" in link:
            link = link.split("&")[0]

        try:

            search = VideosSearch(
                link,
                limit=10,
            )

            response = await search.next()

            result = (
                response.get("result")
                if response
                else []
            )

            if not result:
                raise ValueError(
                    "No YouTube results found"
                )

            if query_type >= len(result):
                query_type = 0

            selected = result[query_type]

            return (
                selected["title"],
                selected["duration"],
                selected["thumbnails"][0]["url"]
                .split("?")[0],
                selected["id"],
            )

        except Exception:

            return (
                "Unknown Title",
                "0:00",
                "https://telegra.ph/file/"
                "2e3d368e77c449c287430.jpg",
                "None",
            )

    # ----------------- DOWNLOAD -----------------

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
    ):

        if videoid:
            link = self.base + link

        try:

            file_title = (
                title
                if isinstance(title, str)
                else None
            )

            if video:
                downloaded_file = await download_video(
                    link,
                    title=file_title,
                )
            else:
                downloaded_file = await download_song(
                    link,
                    title=file_title,
                )

            if downloaded_file:
                return downloaded_file, True

            return None, False

        except Exception as e:

            LOGGER.error(
                f"Error in YouTubeAPI.download: {e}"
            )

            return None, False

    # ----------------- AUTOPLAY -----------------

    async def autoplay(
        self,
        last_vidid: str,
        title: str,
        max_duration: int = None,
    ):

        try:

            import random

            search_query = (
                f"{title} official audio"
            )

            valid_choices = []

            # ----------------- PYTUBE SEARCH -----------------

            try:

                search = VideosSearch(
                    search_query,
                    limit=15,
                )

                result = await search.next()

                if result and result.get("result"):

                    for res in result["result"]:

                        vidid = str(
                            res.get("id") or ""
                        )

                        if (
                            not vidid
                            or vidid == "None"
                            or vidid == last_vidid
                        ):
                            continue

                        dur_str = str(
                            res.get(
                                "duration",
                                "0:00",
                            )
                        )

                        dur_sec = 0

                        if dur_str and ":" in dur_str:

                            parts = dur_str.split(":")

                            try:

                                if len(parts) == 2:
                                    dur_sec = (
                                        int(parts[0]) * 60
                                        + int(parts[1])
                                    )

                                elif len(parts) == 3:
                                    dur_sec = (
                                        int(parts[0]) * 3600
                                        + int(parts[1]) * 60
                                        + int(parts[2])
                                    )

                            except (
                                ValueError,
                                TypeError,
                            ):
                                pass

                        if dur_sec < 30:
                            continue

                        if (
                            max_duration
                            and dur_sec > max_duration
                        ):
                            continue

                        valid_choices.append(
                            {
                                "vidid": vidid,
                                "title": str(
                                    res.get(
                                        "title",
                                        "Unknown Title",
                                    )
                                ).title(),
                                "duration_min": dur_str,
                                "duration_sec": dur_sec,
                            }
                        )

            except Exception as e:

                LOGGER.warning(
                    f"VideosSearch autoplay failed: {e}"
                )

            # ----------------- YT-DLP FALLBACK -----------------

            if not valid_choices:

                ytdl_opts = {
                    "quiet": True,
                    "extract_flat": True,
                    "noplaylist": True,
                    "cookiefile": "cookies.txt",
                    "extractor_args": {
                        "youtube": [
                            "player_client=ios,tv_embedded"
                        ]
                    },
                }

                ydl = yt_dlp.YoutubeDL(
                    ytdl_opts
                )

                r = await _async_run(
                    ydl.extract_info,
                    f"ytsearch10:{search_query}",
                    download=False,
                )

                if r and r.get("entries"):

                    for entry in r["entries"]:

                        if not entry:
                            continue

                        vidid = entry.get("id")

                        if (
                            not vidid
                            or vidid == last_vidid
                        ):
                            continue

                        raw_dur = entry.get(
                            "duration",
                            0,
                        )

                        try:

                            dur_sec = int(
                                float(raw_dur)
                            ) if raw_dur else 0

                        except (
                            ValueError,
                            TypeError,
                        ):

                            dur_sec = 0

                        if not dur_sec or dur_sec < 30:
                            continue

                        if (
                            max_duration
                            and dur_sec > max_duration
                        ):
                            continue

                        m, s = divmod(
                            dur_sec,
                            60,
                        )

                        h, m = divmod(
                            m,
                            60,
                        )

                        dur_str = (
                            f"{h}:{m:02d}:{s:02d}"
                            if h
                            else f"{m}:{s:02d}"
                        )

                        valid_choices.append(
                            {
                                "vidid": vidid,
                                "title": str(
                                    entry.get(
                                        "title",
                                        "Unknown Title",
                                    )
                                ).title(),
                                "duration_min": dur_str,
                                "duration_sec": dur_sec,
                            }
                        )

            if valid_choices:
                return random.choice(
                    valid_choices
                )

            return None

        except Exception as e:

            LOGGER.error(
                f"YouTube Autoplay Function Error: {e}"
            )

            return None


# ----------------- GLOBAL INSTANCE -----------------

YouTube = YouTubeAPI()
