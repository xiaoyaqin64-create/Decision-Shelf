from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Callable

from .database import Database
from .deepseek import AIService, DeepSeekClient, DeepSeekConfig
from .engine import DecisionEngine, FeedbackService
from .models import (
    ACTIONS,
    CATEGORIES,
    CATEGORY_ALIASES,
    CATEGORY_LABELS,
    ENERGY_LABELS,
    ENERGY_LEVELS,
    STATUSES,
    Card,
    DecisionContext,
)
from .seed import seed_demo
from .utils import load_env_file, make_card_id, normalize_terms, split_terms


PREFERENCE_CHOICES = [
    "被震撼",
    "轻松愉悦",
    "获得灵感",
    "补经典",
    "专注",
    "排遣情绪",
    "高智商快感",
]

ENERGY_PRESETS = {
    "1": ("low", ["轻松愉悦"]),
    "2": ("medium", []),
    "3": ("low", ["排遣情绪"]),
    "4": ("high", ["拓宽认知"]),
    "5": ("high", ["高智商快感"]),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m decision_shelf",
        description="本地、透明、会从反馈中学习的个人决策书架",
    )
    parser.add_argument("--db", help="SQLite 数据库路径（默认 data/decision_shelf.db）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="初始化本地数据库")
    sub.add_parser("seed-demo", help="导入四类中文示例卡片")

    web = sub.add_parser("web", help="启动本地 Web 应用")
    web.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"))
    web.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", "8000")))
    web.add_argument("--reload", action="store_true", help="开发模式自动重载")

    card_parser = sub.add_parser("card", help="管理决策卡片")
    card_sub = card_parser.add_subparsers(dest="card_command", required=True)
    add = card_sub.add_parser("add", help="添加卡片")
    add.add_argument("--category", choices=CATEGORIES)
    add.add_argument("--title")
    add.add_argument("--duration", type=int, help="总时长（分钟）")
    add.add_argument("--min-session", type=int, help="最小单次投入（分钟）")
    add.add_argument("--tags", help="逗号分隔标签")
    add.add_argument("--moods", help="逗号分隔适合场景")
    add.add_argument("--energy", choices=ENERGY_LEVELS)
    add.add_argument("--priority", type=int, choices=range(1, 6))
    add.add_argument("--notes")
    add.add_argument("--extension-json", help="分类扩展字段 JSON")
    add.add_argument("--ai-tags", action="store_true", help="让 DeepSeek 补充语义标签")

    listing = card_sub.add_parser("list", help="列出卡片")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.add_argument("--status", choices=STATUSES)
    card_sub.add_parser("show", help="查看卡片").add_argument("id")
    card_sub.add_parser("edit", help="交互式编辑卡片").add_argument("id")

    decide = sub.add_parser("decide", help="开始一次决策")
    decide.add_argument("--minutes", type=int)
    decide.add_argument("--energy", choices=ENERGY_LEVELS)
    decide.add_argument("--categories", help="逗号分隔：movie,book,album,game")
    decide.add_argument("--preferences", help="逗号分隔偏好标签")
    decide.add_argument("--moods", help="逗号分隔当前情绪/目标")
    decide.add_argument("--text", default="", help="自由描述当前状态")
    decide.add_argument("--seed", default="default", help="稳定随机种子")
    decide.add_argument("--no-ai", action="store_true", help="不调用 DeepSeek，仅用本地兜底")

    action = sub.add_parser("action", help="对卡片执行开始、完成、跳过等操作")
    action.add_argument("id")
    action.add_argument("action", choices=ACTIONS)
    action.add_argument("--session-id", type=int)
    action.add_argument("--rating", type=float)
    action.add_argument("--review")

    history = sub.add_parser("history", help="查看决策历史")
    history.add_argument("--limit", type=int, default=20)

    prefs = sub.add_parser("prefs", help="查看或重置长期偏好")
    prefs_sub = prefs.add_subparsers(dest="prefs_command", required=True)
    prefs_sub.add_parser("show")
    prefs_sub.add_parser("reset")
    return parser


def main(argv: list[str] | None = None) -> None:
    _configure_console_encoding()
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "web":
        if args.db:
            os.environ["DECISION_SHELF_DB"] = args.db
        import uvicorn

        uvicorn.run(
            "decision_shelf.webapp:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return
    database = Database(args.db)
    try:
        if args.command == "init":
            database.initialize()
            print(f"数据库已初始化：{database.path.resolve()}")
            return

        database.initialize()
        if args.command == "seed-demo":
            added, skipped = seed_demo(database)
            print(f"示例数据导入完成：新增 {added}，已存在 {skipped}")
        elif args.command == "card":
            _handle_card(database, args)
        elif args.command == "decide":
            _handle_decide(database, args)
        elif args.command == "action":
            _handle_action(database, args)
        elif args.command == "history":
            _handle_history(database, args.limit)
        elif args.command == "prefs":
            _handle_prefs(database, args.prefs_command)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"错误：{str(exc).strip(chr(39))}", file=sys.stderr)
        raise SystemExit(2) from exc


def _handle_card(database: Database, args: argparse.Namespace) -> None:
    if args.card_command == "add":
        card = _build_card_interactively(args)
        if args.ai_tags:
            service = AIService()
            suggestion = service.suggest_card_metadata(card)
            card.tags = normalize_terms([*card.tags, *suggestion["tags"]])
            card.mood_fit = normalize_terms([*card.mood_fit, *suggestion["mood_fit"]])
            card.energy_level = suggestion["energy_level"]
            print(f"语义补全来源：{suggestion['source']}")
            if service.last_error:
                print(f"DeepSeek 不可用，保留原输入：{service.last_error}")
        database.add_card(card)
        print(f"已添加：[{card.category_label}] {card.title}（{card.id}）")
    elif args.card_command == "list":
        cards = database.list_cards(category=args.category, status=args.status)
        if not cards:
            print("没有符合条件的卡片。")
            return
        print(f"{'ID':<30} {'分类':<6} {'状态':<12} {'时长':<10} 标题")
        print("-" * 86)
        for card in cards:
            duration = _duration_text(card)
            print(
                f"{card.id:<30} {card.category_label:<6} {card.status:<12} "
                f"{duration:<10} {card.title}"
            )
    elif args.card_command == "show":
        card = _require_card(database, args.id)
        _print_card(card)
    elif args.card_command == "edit":
        card = _require_card(database, args.id)
        _edit_card(card)
        database.update_card(card)
        print(f"已更新：{card.title}")


def _handle_decide(database: Database, args: argparse.Namespace) -> None:
    context = _build_decision_context(args)
    if args.no_ai:
        ai = AIService(DeepSeekClient(DeepSeekConfig(api_key="")))
    else:
        ai = AIService()
    normalized = ai.merge_context(context)
    engine = DecisionEngine(database)
    result = engine.decide(context, persist=False, normalized_context=normalized)
    ai.explain_candidates(result.candidates, context)
    result.session_id = database.save_decision(
        context, result.candidates, normalized_context=normalized
    )

    print(f"\n决策 #{result.session_id}")
    print(
        f"时间 {context.available_minutes} 分钟｜精力 {ENERGY_LABELS[context.energy_level]}｜"
        f"范围 {'、'.join(CATEGORY_LABELS[item] for item in context.categories)}"
    )
    if not result.candidates:
        print("没有卡片通过硬过滤。可以增加可用时间、扩大分类或添加新卡片。")
        return

    for candidate in result.candidates[:1]:
        print(
            f"\n推荐：{candidate.card.title} "
            f"[{candidate.card.category_label}]  {candidate.total_score:.2f} 分"
        )
        print(f"理由：{candidate.explanation}")
        breakdown = " / ".join(
            f"{key} {value:g}" for key, value in candidate.scores.items()
        )
        print(f"基础分：{breakdown}")
        if candidate.adjustments:
            adjustment = " / ".join(
                f"{key} {value:+g}" for key, value in candidate.adjustments.items()
            )
            print(f"修正：{adjustment}")
    if ai.last_error:
        print(f"\n提示：DeepSeek 未参与本次输出，已使用本地兜底（{ai.last_error}）。")
    print(
        "\n下一步示例："
        f"python -m decision_shelf action {result.candidates[0].card.id} start "
        f"--session-id {result.session_id}"
    )


def _handle_action(database: Database, args: argparse.Namespace) -> None:
    rating = args.rating
    review = args.review
    if args.action == "complete" and rating is None and sys.stdin.isatty():
        rating = _optional_float(input("评分 0～10（可留空，最多一位小数）："), minimum=0, maximum=10)
        if review is None:
            review = input("感想（可留空）：").strip() or None
    card = FeedbackService(database).apply(
        args.id,
        args.action,
        session_id=args.session_id,
        rating=rating,
        review=review,
    )
    print(f"已记录 {args.action}：{card.title}，当前状态 {card.status}")


def _handle_history(database: Database, limit: int) -> None:
    history = database.list_history(limit)
    if not history:
        print("还没有决策历史。")
        return
    for item in history:
        categories = "、".join(CATEGORY_LABELS.get(value, value) for value in item["categories"])
        print(
            f"#{item['id']}  {item['created_at']}  {item['available_minutes']} 分钟  "
            f"{ENERGY_LABELS.get(item['energy_level'], item['energy_level'])}精力  {categories}"
        )
        print(f"  推荐：{item['primary_title'] or '无符合条件内容'}")
        if item["preferences"] or item["moods"]:
            state_terms = normalize_terms(item["preferences"] + item["moods"])
            print(f"  状态：{'、'.join(state_terms)}")
        if item["free_text"]:
            print(f"  描述：{item['free_text']}")
        for interaction in item["interactions"]:
            detail = f"  结果：{interaction['action']} · {interaction['card_title']}"
            if interaction["rating"] is not None:
                detail += f" · {interaction['rating']:.1f}/10"
            print(detail)
            if interaction["review"]:
                print(f"  反馈：{interaction['review']}")


def _handle_prefs(database: Database, command: str) -> None:
    if command == "reset":
        database.reset_preferences()
        print("长期偏好权重已重置。")
        return
    weights = database.get_preference_weights()
    if not weights:
        print("还没有学习到长期偏好。")
        return
    for (key_type, key), weight in sorted(weights.items()):
        print(f"{key_type:<10} {key:<20} {weight:+.2f}")


def _build_card_interactively(args: argparse.Namespace) -> Card:
    category = args.category or _ask_category(single=True)[0]
    title = args.title or _required_input("标题：")
    duration = args.duration
    if duration is None:
        duration = _optional_int(input("预计总时长（分钟，可留空）："), minimum=1)
    min_session = args.min_session
    if category in {"book", "game"} and min_session is None:
        min_session = _optional_int(input("最小单次投入（分钟，可留空）："), minimum=1)
    tags = split_terms(args.tags) if args.tags is not None else split_terms(input("标签（逗号分隔，可留空）："))
    moods = split_terms(args.moods) if args.moods is not None else split_terms(input("适合场景（逗号分隔，可留空）："))
    energy = args.energy or _ask_energy_simple()
    priority = args.priority or _optional_int(
        input("优先级 1～5（默认 3）："), minimum=1, maximum=5
    ) or 3
    notes = args.notes if args.notes is not None else input("备注（可留空）：").strip()
    extension = _extension_for_category(category)
    if args.extension_json:
        extension.update(json.loads(args.extension_json))
    return Card(
        id=make_card_id(category, title),
        category=category,
        title=title,
        duration_minutes=duration,
        min_session_minutes=min_session,
        tags=tags,
        energy_level=energy,
        mood_fit=moods,
        notes=notes,
        priority=priority,
        extension=extension,
    )


def _build_decision_context(args: argparse.Namespace) -> DecisionContext:
    minutes = args.minutes or _ask_minutes()
    inferred_moods: list[str] = []
    if args.energy:
        energy = args.energy
    else:
        print("\n我现在的精力：")
        print("1. 很累，只想轻松")
        print("2. 还行，可以投入")
        print("3. 精力低，同时希望排遣情绪")
        print("4. 很清醒，想学到点什么")
        print("5. 想挑战一下自己的脑子")
        choice = _choice_input("选择 1～5：", set(ENERGY_PRESETS))
        energy, inferred_moods = ENERGY_PRESETS[choice]
    categories = (
        _parse_categories(args.categories)
        if args.categories
        else _ask_category(single=False)
    )
    preferences = (
        split_terms(args.preferences)
        if args.preferences is not None
        else _ask_preferences()
    )
    moods = split_terms(args.moods) if args.moods is not None else []
    moods = normalize_terms([*moods, *inferred_moods, *preferences])
    text = args.text
    if not text and sys.stdin.isatty():
        text = input("补充描述当前状态（可留空）：").strip()
    return DecisionContext(
        available_minutes=minutes,
        energy_level=energy,
        categories=categories,
        preferences=preferences,
        moods=moods,
        free_text=text,
        seed=args.seed,
    )


def _ask_minutes() -> int:
    print("\n我现在有多少时间？")
    print("1. 30 分钟以内（30）")
    print("2. 1 小时（60）")
    print("3. 2 小时（120）")
    print("4. 半天（240）")
    print("5. 一整天（480）")
    print("也可以直接输入分钟数。")
    value = _required_input("选择或输入分钟：")
    presets = {"1": 30, "2": 60, "3": 120, "4": 240, "5": 480}
    if value in presets:
        return presets[value]
    return _positive_int(value, "可用时间")


def _ask_category(*, single: bool) -> list[str]:
    print("\n内容类型：1. 电影  2. 书籍  3. 专辑  4. 游戏  5. 都可以")
    value = _required_input("选择（可用逗号多选）：")
    number_map = {"1": "movie", "2": "book", "3": "album", "4": "game"}
    if value == "5":
        return list(CATEGORIES)
    selected: list[str] = []
    for token in split_terms(value):
        category = number_map.get(token) or CATEGORY_ALIASES.get(token.casefold())
        if not category:
            raise ValueError(f"无法识别分类：{token}")
        selected.append(category)
    selected = normalize_terms(selected)
    if single and len(selected) != 1:
        raise ValueError("添加卡片时只能选择一个分类")
    return selected


def _ask_preferences() -> list[str]:
    print("\n我现在偏好（可多选）：")
    for index, label in enumerate(PREFERENCE_CHOICES, start=1):
        print(f"{index}. {label}")
    raw = input("输入编号并用逗号分隔；可留空：").strip()
    if not raw:
        return []
    selected: list[str] = []
    for token in split_terms(raw):
        if token.isdigit() and 1 <= int(token) <= len(PREFERENCE_CHOICES):
            selected.append(PREFERENCE_CHOICES[int(token) - 1])
        else:
            selected.append(token)
    return normalize_terms(selected)


def _ask_energy_simple() -> str:
    print("精力要求：1. 低  2. 中等  3. 高")
    return {"1": "low", "2": "medium", "3": "high"}[
        _choice_input("选择 1～3（默认 2）：", {"1", "2", "3"}, default="2")
    ]


def _extension_for_category(category: str) -> dict[str, Any]:
    fields: dict[str, list[tuple[str, str]]] = {
        "movie": [("director", "导演"), ("year", "年份"), ("country", "国家")],
        "book": [("author", "作者"), ("difficulty", "阅读难度")],
        "album": [("artist", "艺术家"), ("style", "风格")],
        "game": [("platform", "平台"), ("intensity", "操作强度")],
    }
    result: dict[str, Any] = {}
    for key, label in fields[category]:
        value = input(f"{label}（可留空）：").strip()
        if value:
            result[key] = int(value) if key == "year" and value.isdigit() else value
    return result


def _edit_card(card: Card) -> None:
    card.title = _edit_value("标题", card.title, str)
    card.duration_minutes = _edit_optional_int("总时长", card.duration_minutes)
    if card.category in {"book", "game"}:
        card.min_session_minutes = _edit_optional_int(
            "最小单次投入", card.min_session_minutes
        )
    tags = input(f"标签 [{', '.join(card.tags)}]：").strip()
    if tags:
        card.tags = split_terms(tags)
    moods = input(f"适合场景 [{', '.join(card.mood_fit)}]：").strip()
    if moods:
        card.mood_fit = split_terms(moods)
    energy = input(f"精力 low/medium/high [{card.energy_level}]：").strip()
    if energy:
        card.energy_level = energy
    priority = input(f"优先级 1～5 [{card.priority}]：").strip()
    if priority:
        card.priority = _positive_int(priority, "优先级")
    notes = input(f"备注 [{card.notes}]：").strip()
    if notes:
        card.notes = notes


def _print_card(card: Card) -> None:
    print(f"ID：{card.id}")
    print(f"分类：{card.category_label}")
    print(f"标题：{card.title}")
    print(f"状态：{card.status}")
    print(f"时长：{_duration_text(card)}")
    print(f"标签：{'、'.join(card.tags) or '无'}")
    print(f"适合：{'、'.join(card.mood_fit) or '无'}")
    print(f"精力：{ENERGY_LABELS[card.energy_level]}")
    print(f"优先级：{card.priority}{'（近期优先）' if card.is_prioritized else ''}")
    print(f"扩展字段：{json.dumps(card.extension, ensure_ascii=False)}")
    if card.notes:
        print(f"备注：{card.notes}")
    if card.rating is not None:
        print(f"评分：{card.rating:.1f}/10")
    if card.review:
        print(f"感想：{card.review}")


def _duration_text(card: Card) -> str:
    if card.category in {"book", "game"} and card.min_session_minutes:
        return f"{card.duration_minutes or '?'} / ≥{card.min_session_minutes}m"
    return f"{card.duration_minutes}m" if card.duration_minutes else "未知"


def _parse_categories(raw: str) -> list[str]:
    result: list[str] = []
    for token in split_terms(raw):
        category = CATEGORY_ALIASES.get(token.casefold())
        if not category:
            raise ValueError(f"无法识别分类：{token}")
        result.append(category)
    return normalize_terms(result)


def _require_card(database: Database, card_id: str) -> Card:
    card = database.get_card(card_id)
    if not card:
        raise KeyError(f"没有找到卡片：{card_id}")
    return card


def _required_input(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        raise ValueError("输入不能为空")
    return value


def _choice_input(prompt: str, allowed: set[str], default: str | None = None) -> str:
    value = input(prompt).strip() or default
    if value not in allowed:
        raise ValueError(f"请选择：{', '.join(sorted(allowed))}")
    return value


def _positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label}必须是整数") from exc
    if parsed <= 0:
        raise ValueError(f"{label}必须大于 0")
    return parsed


def _optional_int(value: str, *, minimum: int, maximum: int | None = None) -> int | None:
    if not value.strip():
        return None
    parsed = _positive_int(value, "数值")
    if not math.isfinite(parsed) or parsed < minimum or (maximum is not None and parsed > maximum):
        end = f"～{maximum}" if maximum is not None else "以上"
        raise ValueError(f"数值必须在 {minimum}{end}")
    return parsed


def _optional_float(value: str, *, minimum: float, maximum: float | None = None) -> float | None:
    if not value.strip():
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError("请输入数字") from exc
    if parsed < minimum or (maximum is not None and parsed > maximum):
        end = f"～{maximum:g}" if maximum is not None else "以上"
        raise ValueError(f"数值必须在 {minimum:g}{end}")
    if abs(parsed * 10 - round(parsed * 10)) > 1e-8:
        raise ValueError("评分最多保留一位小数")
    return parsed


def _edit_value(label: str, current: Any, cast: Callable[[str], Any]) -> Any:
    value = input(f"{label} [{current}]：").strip()
    return cast(value) if value else current


def _edit_optional_int(label: str, current: int | None) -> int | None:
    value = input(f"{label}（分钟） [{current or '未知'}]：").strip()
    return _positive_int(value, label) if value else current


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
