from __future__ import annotations

import sqlite3
from datetime import timedelta

from .database import Database
from .models import Card
from .utils import now_local


def demo_cards() -> list[Card]:
    created = (now_local() - timedelta(days=120)).isoformat(timespec="seconds")
    return [
        Card(
            id="movie_inception",
            category="movie",
            title="盗梦空间",
            duration_minutes=148,
            tags=["科幻", "视效", "创意", "商业片", "高智商快感"],
            energy_level="high",
            mood_fit=["被震撼", "专注", "获得灵感"],
            priority=4,
            notes="很久以前就想重看",
            extension={"director": "克里斯托弗·诺兰", "year": 2010, "country": "美国"},
            created_at=created,
        ),
        Card(
            id="movie_blade_runner_2049",
            category="movie",
            title="银翼杀手2049",
            duration_minutes=164,
            tags=["科幻", "氛围", "视效", "哲思"],
            energy_level="medium",
            mood_fit=["被震撼", "获得灵感", "排遣情绪"],
            priority=3,
            extension={"director": "丹尼斯·维伦纽瓦", "year": 2017},
            created_at=created,
        ),
        Card(
            id="movie_grand_budapest",
            category="movie",
            title="布达佩斯大饭店",
            duration_minutes=100,
            tags=["喜剧", "美学", "轻松", "创意"],
            energy_level="low",
            mood_fit=["轻松愉悦", "获得灵感"],
            priority=3,
            extension={"director": "韦斯·安德森", "year": 2014},
            created_at=created,
        ),
        Card(
            id="book_thinking_fast_slow",
            category="book",
            title="思考，快与慢",
            duration_minutes=1200,
            min_session_minutes=25,
            tags=["心理学", "认知", "经典", "高智商快感"],
            energy_level="high",
            mood_fit=["拓宽认知", "专注", "补经典"],
            priority=4,
            extension={"author": "丹尼尔·卡尼曼", "difficulty": "high"},
            created_at=created,
        ),
        Card(
            id="book_invisible_cities",
            category="book",
            title="看不见的城市",
            duration_minutes=360,
            min_session_minutes=15,
            tags=["文学", "想象力", "短章", "创意"],
            energy_level="medium",
            mood_fit=["获得灵感", "排遣情绪"],
            priority=3,
            extension={"author": "伊塔洛·卡尔维诺", "difficulty": "medium"},
            created_at=created,
        ),
        Card(
            id="book_little_prince",
            category="book",
            title="小王子",
            duration_minutes=120,
            min_session_minutes=15,
            tags=["文学", "经典", "治愈", "轻松"],
            energy_level="low",
            mood_fit=["轻松愉悦", "排遣情绪", "补经典"],
            priority=2,
            extension={"author": "安托万·德·圣-埃克苏佩里", "difficulty": "low"},
            created_at=created,
        ),
        Card(
            id="album_dark_side",
            category="album",
            title="The Dark Side of the Moon",
            duration_minutes=43,
            tags=["前卫摇滚", "经典", "概念专辑", "氛围"],
            energy_level="medium",
            mood_fit=["被震撼", "专注", "补经典"],
            priority=4,
            extension={"artist": "Pink Floyd", "year": 1973},
            created_at=created,
        ),
        Card(
            id="album_nurture",
            category="album",
            title="Nurture",
            duration_minutes=59,
            tags=["电子", "治愈", "创意", "制作灵感"],
            energy_level="medium",
            mood_fit=["获得灵感", "轻松愉悦", "排遣情绪"],
            priority=3,
            extension={"artist": "Porter Robinson", "year": 2021},
            created_at=created,
        ),
        Card(
            id="album_kind_of_blue",
            category="album",
            title="Kind of Blue",
            duration_minutes=46,
            tags=["爵士", "经典", "即兴", "氛围"],
            energy_level="low",
            mood_fit=["轻松愉悦", "获得灵感", "补经典"],
            priority=3,
            extension={"artist": "Miles Davis", "year": 1959},
            created_at=created,
        ),
        Card(
            id="game_outer_wilds",
            category="game",
            title="Outer Wilds",
            duration_minutes=960,
            min_session_minutes=45,
            tags=["探索", "解谜", "科幻", "高智商快感"],
            energy_level="high",
            mood_fit=["被震撼", "拓宽认知", "获得灵感"],
            priority=5,
            extension={"platform": ["PC"], "intensity": "medium"},
            created_at=created,
        ),
        Card(
            id="game_dorfromantik",
            category="game",
            title="Dorfromantik",
            duration_minutes=600,
            min_session_minutes=20,
            tags=["休闲", "拼图", "治愈", "建造"],
            energy_level="low",
            mood_fit=["轻松愉悦", "排遣情绪"],
            priority=3,
            extension={"platform": ["PC", "Switch"], "intensity": "low"},
            created_at=created,
        ),
        Card(
            id="game_disco_elysium",
            category="game",
            title="极乐迪斯科",
            duration_minutes=1800,
            min_session_minutes=60,
            tags=["角色扮演", "文学", "推理", "高智商快感"],
            energy_level="high",
            mood_fit=["拓宽认知", "专注", "排遣情绪"],
            priority=4,
            extension={"platform": ["PC"], "intensity": "medium"},
            created_at=created,
        ),
    ]


def seed_demo(database: Database) -> tuple[int, int]:
    added = 0
    skipped = 0
    for card in demo_cards():
        try:
            database.add_card(card)
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    return added, skipped
