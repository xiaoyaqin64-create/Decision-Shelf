from __future__ import annotations

import re
from collections.abc import Iterable


GENRE_TAGS: dict[str, list[str]] = {
    "movie": ["惊悚", "悬疑", "历史", "爱情", "科幻", "犯罪", "喜剧", "恐怖", "动作", "剧情", "动画", "纪录片", "战争", "奇幻", "冒险", "音乐"],
    "book": ["文学", "推理", "科幻", "奇幻", "历史", "哲学", "心理学", "科普", "社科", "商业", "传记", "诗歌", "散文"],
    "album": ["流行", "摇滚", "电子", "爵士", "古典", "嘻哈", "民谣", "金属", "R&B", "实验", "氛围", "原声"],
    "game": ["RPG", "动作", "冒险", "解谜", "策略", "模拟", "生存", "恐怖", "叙事", "开放世界", "独立", "休闲", "多人"],
}
SCENE_TAGS = ["轻松", "专注", "宣泄", "灵感", "震撼", "挑战", "陪伴", "学习", "沉浸"]

_SYNONYMS = {
    "放松": "轻松", "轻松愉悦": "轻松", "治愈": "轻松", "解压": "轻松",
    "集中精力": "专注", "想集中精力": "专注", "专心": "专注",
    "排遣情绪": "宣泄", "情绪释放": "宣泄", "表达": "宣泄",
    "获得灵感": "灵感", "创意感知": "灵感", "创作": "灵感", "启发": "灵感",
    "被震撼": "震撼", "想被震撼": "震撼", "视觉冲击": "震撼", "拓宽认知": "震撼",
    "高智商快感": "挑战", "烧脑": "挑战", "挑战脑子": "挑战", "结构复杂": "挑战",
    "陪伴感": "陪伴", "背景播放": "陪伴", "想学到点什么": "学习", "知识": "学习",
    "代入感": "沉浸", "氛围感": "沉浸", "沉浸体验": "沉浸",
    "thriller": "惊悚", "mystery": "悬疑", "sciencefiction": "科幻", "sci-fi": "科幻",
    "romance": "爱情", "crime": "犯罪", "comedy": "喜剧", "horror": "恐怖",
    "action": "动作", "drama": "剧情", "animation": "动画", "documentary": "纪录片",
    "war": "战争", "fantasy": "奇幻", "adventure": "冒险", "music": "音乐",
    "rock": "摇滚", "electronic": "电子", "jazz": "爵士", "classical": "古典",
    "hiphop": "嘻哈", "folk": "民谣", "metal": "金属", "ambient": "氛围",
    "soundtrack": "原声", "roleplaying": "RPG", "role-playing": "RPG",
}


def title_key(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())


def canonical_tag(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    compact = re.sub(r"[\s_]+", "", raw).casefold()
    return _SYNONYMS.get(raw.casefold(), _SYNONYMS.get(compact, raw))


def canonicalize(values: Iterable[str], allowed: Iterable[str] | None = None) -> list[str]:
    allowed_map = {item.casefold(): item for item in allowed or []}
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = canonical_tag(str(value))
        if allowed_map:
            normalized = allowed_map.get(normalized.casefold(), "")
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def taxonomy_payload() -> dict[str, object]:
    return {"genres": GENRE_TAGS, "scenes": SCENE_TAGS}
