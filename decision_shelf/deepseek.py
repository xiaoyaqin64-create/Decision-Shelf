from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .models import CATEGORIES, Candidate, Card, DecisionContext, ENERGY_LEVELS
from .taxonomy import GENRE_TAGS, SCENE_TAGS, canonicalize
from .utils import normalize_terms


class DeepSeekError(RuntimeError):
    pass


Transport = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class DeepSeekConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout_seconds: float = 20.0
    json_retries: int = 1

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT", "20")),
            json_retries=max(0, int(os.getenv("DEEPSEEK_JSON_RETRIES", "1"))),
        )


class DeepSeekClient:
    def __init__(
        self,
        config: DeepSeekConfig | None = None,
        *,
        transport: Transport | None = None,
    ):
        self.config = config or DeepSeekConfig.from_env()
        self.transport = transport

    @property
    def available(self) -> bool:
        return bool(self.config.api_key or self.transport)

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        if not self.available:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY")
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        last_format_error: DeepSeekError | None = None
        for attempt in range(self.config.json_retries + 1):
            if attempt:
                payload["messages"][-1]["content"] += (
                    "\n请重试：务必只输出一个非空、可解析的 JSON 对象。"
                )
            try:
                response = self.transport(payload) if self.transport else self._post(payload)
                message = response["choices"][0]["message"]
                content = message.get("content")
                return self._parse_json_content(content)
            except (TimeoutError, urllib.error.URLError) as exc:
                raise DeepSeekError(f"DeepSeek 请求失败：{exc}") from exc
            except (KeyError, IndexError, TypeError) as exc:
                last_format_error = DeepSeekError(f"DeepSeek 响应结构无效：{exc}")
            except json.JSONDecodeError as exc:
                last_format_error = DeepSeekError(
                    f"DeepSeek content 不是有效 JSON：{exc.msg}"
                )
            except DeepSeekError as exc:
                last_format_error = exc

        attempts = self.config.json_retries + 1
        raise DeepSeekError(
            f"{last_format_error}（共尝试 {attempts} 次，已自动使用本地兜底）"
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise DeepSeekError(f"DeepSeek HTTP {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DeepSeekError(f"DeepSeek 请求失败：{exc}") from exc

    @staticmethod
    def _parse_json_content(content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise DeepSeekError("DeepSeek content 不是字符串或对象")
        cleaned = content.strip()
        if not cleaned:
            raise DeepSeekError("DeepSeek 返回了空 content")
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise DeepSeekError("DeepSeek JSON 顶层必须是对象")
        return parsed


class AIService:
    def __init__(self, client: DeepSeekClient | None = None):
        self.client = client or DeepSeekClient()
        self.last_error: str | None = None

    def analyze_context(self, text: str) -> dict[str, Any]:
        self.last_error = None
        if not text.strip():
            return {"energy_level": None, "moods": [], "preferences": [], "source": "none"}
        try:
            response = self.client.chat_json(
                system=(
                    "你是个人活动决策器的语义解析模块。只输出 JSON，不推荐具体内容。"
                    "energy_level 只能是 low、medium、high；moods 和 preferences 都是简短中文标签数组。"
                ),
                user=(
                    "解析这段当前状态描述：\n"
                    f"{text}\n"
                    "返回格式：{\"energy_level\":\"low|medium|high\","
                    "\"moods\":[...],\"preferences\":[...]}"
                ),
                max_tokens=300,
            )
            energy = response.get("energy_level")
            if energy not in ENERGY_LEVELS:
                energy = None
            return {
                "energy_level": energy,
                "moods": canonicalize(_safe_string_list(response.get("moods")), SCENE_TAGS),
                "preferences": normalize_terms(
                    _safe_string_list(response.get("preferences"))
                ),
                "source": "deepseek",
            }
        except DeepSeekError as exc:
            self.last_error = str(exc)
            fallback = self._fallback_context(text)
            fallback["source"] = "local-fallback"
            return fallback

    def merge_context(self, context: DecisionContext) -> dict[str, Any]:
        analyzed = self.analyze_context(context.free_text)
        context.moods = canonicalize([*context.moods, *analyzed["moods"]], SCENE_TAGS)
        context.genre_preferences = [item for item in canonicalize([*context.genre_preferences, *context.preferences, *analyzed["preferences"]]) if item not in SCENE_TAGS]
        return analyzed

    def explain_candidates(
        self, candidates: list[Candidate], context: DecisionContext
    ) -> list[Candidate]:
        shown = candidates[:1]
        if not shown:
            return candidates
        compact = [
            {
                "id": item.card.id,
                "title": item.card.title,
                "category": item.card.category_label,
                "required_minutes": item.card.required_minutes,
                "tags": item.card.tags,
                "mood_fit": item.card.mood_fit,
                "total_score": item.total_score,
                "scores": item.scores,
                "adjustments": item.adjustments,
            }
            for item in shown
        ]
        try:
            response = self.client.chat_json(
                system=(
                    "你负责解释一个本地规则引擎已经排好的推荐。不得改变顺序，不得虚构卡片信息。"
                    "每条理由控制在 80 个中文字符内，只输出 JSON。"
                ),
                user=json.dumps(
                    {
                        "context": {
                            "available_minutes": context.available_minutes,
                            "energy_level": context.energy_level,
                            "moods": context.moods,
                            "preferences": context.preferences,
                        },
                        "ordered_candidates": compact,
                        "output": {"explanations": [{"id": "卡片id", "reason": "理由"}]},
                    },
                    ensure_ascii=False,
                ),
                max_tokens=600,
            )
            explanations = {
                str(item.get("id")): str(item.get("reason", "")).strip()
                for item in response.get("explanations", [])
                if isinstance(item, dict)
            }
            for item in shown:
                item.explanation = explanations.get(item.card.id) or self._template_explanation(
                    item, context
                )
        except DeepSeekError as exc:
            self.last_error = str(exc)
            for item in shown:
                item.explanation = self._template_explanation(item, context)
        return candidates

    def suggest_card_metadata(self, card: Card) -> dict[str, Any]:
        self.last_error = None
        allowed = GENRE_TAGS[card.category]
        request = {
            "category": card.category_label, "title": card.title,
            "description": card.description, "external_facts": card.extension,
            "known_tags": card.tags, "existing_scenes": card.mood_fit, "notes": card.notes,
            "allowed_genres": allowed, "allowed_scenes": SCENE_TAGS,
            "output": {"tags": ["从 allowed_genres 选择"], "mood_fit": ["从 allowed_scenes 选择"], "energy_level": "low|medium|high"},
        }
        last: DeepSeekError | None = None
        for attempt in range(2):
            try:
                response = self.client.chat_json(
                    system="你为决策卡片补充受控语义标签。不得编造事实字段，标签只能来自给定词表，只输出 JSON。",
                    user=json.dumps(request, ensure_ascii=False) + ("\n上次没有产生可用字段，请纠正并返回非空标准标签。" if attempt else ""),
                    max_tokens=350,
                )
                energy = response.get("energy_level")
                tags = canonicalize(_safe_string_list(response.get("tags")), allowed)
                moods = canonicalize(_safe_string_list(response.get("mood_fit")), SCENE_TAGS)
                if not tags and not moods and (energy not in ENERGY_LEVELS or energy == card.energy_level):
                    raise DeepSeekError("DeepSeek 没有返回可用的新字段")
                return {"tags": tags, "mood_fit": moods, "energy_level": energy if energy in ENERGY_LEVELS else card.energy_level, "source": "deepseek", "retried": bool(attempt)}
            except DeepSeekError as exc:
                last = exc
        self.last_error = str(last or "AI 补全失败")
        return {"tags": card.tags, "mood_fit": card.mood_fit, "energy_level": card.energy_level, "source": "local-fallback", "retried": True}

    def generate_exploration_candidates(
        self,
        context: DecisionContext,
        *,
        excluded_titles: list[str],
        count: int = 12,
    ) -> list[dict[str, Any]]:
        """Generate real-world discovery ideas. Unlike explanations, this has no fake fallback."""
        response = self.client.chat_json(
            system=(
                "你是个人文化娱乐探索助手。只推荐现实中确实存在的电影、书籍、专辑或游戏，"
                "标题必须准确，不能虚构。遵守给定分类、时间和状态约束，不要推荐排除列表中的内容。"
                "只输出 JSON。"
            ),
            user=json.dumps(
                {
                    "context": {
                        "available_minutes": context.available_minutes,
                        "energy_level": context.energy_level,
                        "categories": context.categories,
                        "moods": context.moods,
                        "genre_preferences": context.genre_preferences or context.preferences,
                        "free_text": context.free_text,
                    },
                    "excluded_titles": excluded_titles[:300],
                    "requested_count": count,
                    "output": {
                        "suggestions": [
                            {
                                "category": "movie|book|album|game",
                                "title": "准确标题",
                                "creator": "导演、作者、艺术家或工作室",
                                "year": 2020,
                                "reason": "为什么适合现在",
                                "tags": ["标签"],
                                "mood_fit": ["适合场景"],
                                "energy_level": "low|medium|high",
                                "duration_minutes": 120,
                                "min_session_minutes": 30,
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            max_tokens=1400,
        )
        suggestions: list[dict[str, Any]] = []
        for raw in response.get("suggestions", []):
            if not isinstance(raw, dict):
                continue
            category = str(raw.get("category", "")).strip()
            title = str(raw.get("title", "")).strip()
            if category not in CATEGORIES or category not in context.categories or not title:
                continue
            energy = raw.get("energy_level")
            suggestions.append(
                {
                    "category": category,
                    "title": title,
                    "creator": str(raw.get("creator", "")).strip(),
                    "year": raw.get("year") if isinstance(raw.get("year"), int) else None,
                    "reason": str(raw.get("reason", "")).strip(),
                    "tags": canonicalize(_safe_string_list(raw.get("tags")), GENRE_TAGS[category]),
                    "mood_fit": canonicalize(_safe_string_list(raw.get("mood_fit")), SCENE_TAGS),
                    "energy_level": energy if energy in ENERGY_LEVELS else "medium",
                    "duration_minutes": _positive_optional_int(raw.get("duration_minutes")),
                    "min_session_minutes": _positive_optional_int(
                        raw.get("min_session_minutes")
                    ),
                }
            )
        return suggestions[:count]

    @staticmethod
    def _fallback_context(text: str) -> dict[str, Any]:
        lowered = text.casefold()
        moods: list[str] = []
        preferences: list[str] = []
        energy: str | None = None
        rules = [
            (("累", "疲惫", "轻松"), "low", "轻松"),
            (("情绪", "难过", "排遣"), "low", "宣泄"),
            (("灵感", "创意"), None, "灵感"),
            (("震撼", "击中", "拓宽"), None, "震撼"),
            (("学习", "学点", "认知"), "high", "学习"),
            (("挑战", "烧脑", "聪明"), "high", "挑战"),
            (("专注", "集中"), "medium", "专注"),
            (("经典", "补课"), None, "补经典"),
        ]
        for keywords, inferred_energy, label in rules:
            if any(keyword in lowered for keyword in keywords):
                moods.append(label)
                preferences.append(label)
                energy = inferred_energy or energy
        return {
            "energy_level": energy,
            "moods": normalize_terms(moods),
            "preferences": normalize_terms(preferences),
        }

    @staticmethod
    def _template_explanation(candidate: Candidate, context: DecisionContext) -> str:
        reasons: list[str] = []
        required = candidate.card.required_minutes
        if required:
            reasons.append(f"你有 {context.available_minutes} 分钟，它适合投入约 {required} 分钟")
        if candidate.scores.get("energy", 0) >= 18:
            reasons.append("精力强度与当前状态匹配")
        matches = _matching_terms(
            [*context.moods, *context.preferences],
            [*candidate.card.mood_fit, *candidate.card.tags],
        )
        if matches:
            reasons.append(f"匹配“{'、'.join(matches[:2])}”")
        if candidate.adjustments.get("prioritized"):
            reasons.append("它已被加入近期优先")
        if not reasons:
            reasons.append("它在当前可选内容中的综合匹配度较高")
        return "；".join(reasons) + "。"


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def _matching_terms(left: list[str], right: list[str]) -> list[str]:
    right_map = {term.casefold(): term for term in right}
    return [term for term in left if term.casefold() in right_map]


def _positive_optional_int(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None
