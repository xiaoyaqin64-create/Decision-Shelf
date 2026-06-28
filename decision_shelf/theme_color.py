from __future__ import annotations

import colorsys
import hashlib
import io
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from .database import Database
from .models import Card


MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_HOSTS = {
    "image.tmdb.org",
    "covers.openlibrary.org",
    "coverartarchive.org",
}
ALLOWED_IMAGE_SUFFIXES = (".archive.org", ".openlibrary.org")
PALETTES = {
    "movie": ["#7B3F4A", "#31556E", "#6F4A2F", "#4B536F", "#6A3D62"],
    "book": ["#365F54", "#665338", "#455D3F", "#74483D", "#3F5962"],
    "album": ["#514378", "#713F60", "#335D69", "#6D4B75", "#3D506F"],
    "game": ["#265B65", "#3E4F77", "#375D48", "#70443A", "#4B4270"],
}


def fallback_color(category: str, title: str) -> str:
    palette = PALETTES.get(category, PALETTES["movie"])
    digest = hashlib.sha256(f"{category}:{title}".encode("utf-8")).digest()
    return palette[digest[0] % len(palette)]


def is_allowed_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.casefold()
    return host in ALLOWED_IMAGE_HOSTS or host.endswith(ALLOWED_IMAGE_SUFFIXES)


def extract_theme_color(data: bytes) -> str:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("图片为空或超过 5MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            image.thumbnail((64, 64))
            buckets: Counter[tuple[int, int, int]] = Counter()
            for red, green, blue in image.getdata():
                brightness = (red * 299 + green * 587 + blue * 114) / 1000
                saturation = max(red, green, blue) - min(red, green, blue)
                if brightness < 30 or brightness > 230 or saturation < 12:
                    continue
                buckets[(red // 24 * 24, green // 24 * 24, blue // 24 * 24)] += 1
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("无法解析图片") from exc
    if not buckets:
        raise ValueError("图片没有可用的主题色")
    def score(item: tuple[tuple[int, int, int], int]) -> float:
        (red, green, blue), count = item
        saturation = max(red, green, blue) - min(red, green, blue)
        return count * (1 + saturation / 255)
    red, green, blue = max(buckets.items(), key=score)[0]
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    saturation = max(.38, min(.82, saturation))
    value = max(.28, min(.56, value))
    red, green, blue = (round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, value))
    return f"#{red:02X}{green:02X}{blue:02X}"


class ThemeColorService:
    def __init__(self, database: Database, fetcher: Callable[[str], bytes] | None = None):
        self.database = database
        self.fetcher = fetcher or self._fetch

    def resolve(self, card: Card) -> dict[str, str | bool]:
        if card.theme_color and card.theme_color_source != "pending":
            return {"id": card.id, "theme_color": card.theme_color, "source": card.theme_color_source, "resolved": True}
        color = fallback_color(card.category, card.title)
        source = "fallback"
        if card.image_url and is_allowed_image_url(card.image_url):
            try:
                color = extract_theme_color(self.fetcher(card.image_url))
                source = "extracted"
            except (httpx.HTTPError, TimeoutError, ValueError):
                pass
        updated = self.database.set_theme_color(card.id, color, source)
        return {"id": updated.id, "theme_color": updated.theme_color or color, "source": updated.theme_color_source, "resolved": True}

    def resolve_many(self, cards: list[Card]) -> list[dict[str, str | bool]]:
        if not cards:
            return []
        with ThreadPoolExecutor(max_workers=min(4, len(cards))) as pool:
            return list(pool.map(self.resolve, cards))

    @staticmethod
    def _fetch(url: str) -> bytes:
        with httpx.stream("GET", url, timeout=4.0, follow_redirects=True, headers={"User-Agent": "DecisionShelf/0.4"}) as response:
            response.raise_for_status()
            if not is_allowed_image_url(str(response.url)):
                raise ValueError("图片重定向到了不受信任的域名")
            content_length = int(response.headers.get("content-length", "0") or 0)
            if content_length > MAX_IMAGE_BYTES:
                raise ValueError("图片超过 5MB")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError("图片超过 5MB")
                chunks.append(chunk)
            return b"".join(chunks)
