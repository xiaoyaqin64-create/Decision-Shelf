from __future__ import annotations

import csv
import io
import re
from typing import Any

from pydantic import ValidationError

from .api_schemas import CardDraftSchema
from .database import Database
from .taxonomy import title_key


MAX_IMPORT_BYTES = 256 * 1024
MAX_IMPORT_ROWS = 50

HEADER_ALIASES = {
    "分类": "category",
    "category": "category",
    "标题": "title",
    "title": "title",
    "总时长": "duration_minutes",
    "总时长(分钟)": "duration_minutes",
    "总时长（分钟）": "duration_minutes",
    "duration_minutes": "duration_minutes",
    "最小单次投入": "min_session_minutes",
    "最小单次投入(分钟)": "min_session_minutes",
    "最小单次投入（分钟）": "min_session_minutes",
    "min_session_minutes": "min_session_minutes",
    "标签": "tags",
    "tags": "tags",
    "精力要求": "energy_level",
    "energy_level": "energy_level",
    "适合场景": "mood_fit",
    "mood_fit": "mood_fit",
    "优先级": "priority",
    "priority": "priority",
    "简介": "description",
    "description": "description",
    "备注": "notes",
    "notes": "notes",
    "图片url": "image_url",
    "图片 URL": "image_url",
    "image_url": "image_url",
}

CATEGORY_ALIASES = {
    "movie": "movie",
    "电影": "movie",
    "book": "book",
    "书": "book",
    "书籍": "book",
    "album": "album",
    "专辑": "album",
    "game": "game",
    "游戏": "game",
}

ENERGY_ALIASES = {
    "low": "low",
    "低": "low",
    "medium": "medium",
    "中": "medium",
    "中等": "medium",
    "high": "high",
    "高": "high",
}


def _clean_header(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")


def _split_terms(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[、,，;；]+", value) if part.strip()]


def _positive_int(value: str, label: str, *, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是整数") from exc
    if number <= 0:
        raise ValueError(f"{label}必须大于 0")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label}不能大于 {maximum}")
    return number


def _row_to_draft(values: dict[str, str]) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    provided = [name for name, value in values.items() if value.strip()]
    category_text = values.get("category", "").strip()
    title = values.get("title", "").strip()
    category = CATEGORY_ALIASES.get(category_text.casefold())
    if not category:
        errors.append("分类必须是电影、书籍、专辑、游戏或对应英文值")
    if not title:
        errors.append("标题不能为空")

    data: dict[str, Any] = {
        "category": category or category_text,
        "title": title,
        "source": "manual",
        "external_id": None,
        "description": values.get("description", "").strip(),
        "image_url": values.get("image_url", "").strip() or None,
        "duration_minutes": None,
        "min_session_minutes": None,
        "tags": _split_terms(values.get("tags", "")),
        "energy_level": "medium",
        "mood_fit": _split_terms(values.get("mood_fit", "")),
        "notes": values.get("notes", "").strip(),
        "priority": 3,
        "extension": {},
    }

    for field, label in (
        ("duration_minutes", "总时长"),
        ("min_session_minutes", "最小单次投入"),
    ):
        raw = values.get(field, "").strip()
        if raw:
            try:
                data[field] = _positive_int(raw, label)
            except ValueError as exc:
                errors.append(str(exc))

    raw_priority = values.get("priority", "").strip()
    if raw_priority:
        try:
            data["priority"] = _positive_int(raw_priority, "优先级", maximum=5)
        except ValueError as exc:
            errors.append(str(exc))

    raw_energy = values.get("energy_level", "").strip()
    if raw_energy:
        energy = ENERGY_ALIASES.get(raw_energy.casefold())
        if energy:
            data["energy_level"] = energy
        else:
            errors.append("精力要求必须是低、中等、高或 low、medium、high")

    if not errors:
        try:
            data = CardDraftSchema(**data).dict()
        except ValidationError as exc:
            errors.extend(error.get("msg", "字段不正确") for error in exc.errors())
    return data, provided, errors


def preview_csv_import(content: str, database: Database) -> dict[str, Any]:
    if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("CSV 文件不能超过 256 KB")
    if "\ufffd" in content:
        raise ValueError("CSV 必须使用 UTF-8 或 UTF-8 BOM 编码")

    stream = io.StringIO(content.lstrip("\ufeff"), newline="")
    try:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
    except csv.Error as exc:
        raise ValueError(f"CSV 无法解析：{exc}") from exc
    if not headers:
        raise ValueError("CSV 缺少表头")

    canonical_headers: list[str | None] = []
    unknown_headers: list[str] = []
    seen_headers: set[str] = set()
    for raw_header in headers:
        cleaned = _clean_header(raw_header)
        canonical = HEADER_ALIASES.get(cleaned) or HEADER_ALIASES.get(cleaned.casefold())
        canonical_headers.append(canonical)
        if canonical is None:
            if cleaned:
                unknown_headers.append(cleaned)
            continue
        if canonical in seen_headers:
            raise ValueError(f"CSV 存在重复列：{cleaned}")
        seen_headers.add(canonical)
    missing = [name for name in ("category", "title") if name not in seen_headers]
    if missing:
        labels = "、".join("分类" if name == "category" else "标题" for name in missing)
        raise ValueError(f"CSV 缺少必填列：{labels}")

    rows: list[dict[str, Any]] = []
    seen_titles: set[tuple[str, str]] = set()
    data_count = 0
    try:
        for raw_row in reader:
            cells = [
                part
                for value in raw_row.values()
                for part in (value if isinstance(value, list) else [value])
                if part is not None
            ]
            if not any(str(value).strip() for value in cells):
                continue
            data_count += 1
            if data_count > MAX_IMPORT_ROWS:
                raise ValueError("CSV 一次最多导入 50 条非空数据")
            if None in raw_row:
                rows.append({
                    "row_number": reader.line_num,
                    "raw": {},
                    "draft": None,
                    "provided_fields": [],
                    "status": "invalid",
                    "errors": ["该行的列数多于表头，请检查未加引号的逗号"],
                    "existing_card": None,
                })
                continue
            values: dict[str, str] = {}
            for index, raw_header in enumerate(headers):
                canonical = canonical_headers[index]
                if canonical:
                    values[canonical] = (raw_row.get(raw_header) or "").strip()
            draft, provided, errors = _row_to_draft(values)
            status = "invalid" if errors else "valid"
            existing_payload = None
            if status == "valid":
                identity = (draft["category"], title_key(draft["title"]))
                existing = database.find_by_title(draft["category"], draft["title"])
                if identity in seen_titles:
                    status = "duplicate"
                    errors.append("与文件中前面的卡片重复")
                elif existing:
                    status = "duplicate"
                    errors.append("书架中已存在同分类同标题卡片")
                    existing_payload = {
                        "id": existing.id,
                        "title": existing.title,
                        "category": existing.category,
                        "status": existing.status,
                    }
                else:
                    seen_titles.add(identity)
            rows.append({
                "row_number": reader.line_num,
                "raw": {str(key): value or "" for key, value in raw_row.items()},
                "draft": draft if status != "invalid" else None,
                "provided_fields": provided,
                "status": status,
                "errors": errors,
                "existing_card": existing_payload,
            })
    except csv.Error as exc:
        raise ValueError(f"CSV 无法解析：{exc}") from exc

    if not rows:
        raise ValueError("CSV 中没有可读取的数据行")
    summary = {
        "total": len(rows),
        "valid": sum(row["status"] == "valid" for row in rows),
        "duplicate": sum(row["status"] == "duplicate" for row in rows),
        "invalid": sum(row["status"] == "invalid" for row in rows),
    }
    warnings = []
    if unknown_headers:
        warnings.append(f"已忽略未知列：{'、'.join(unknown_headers)}")
    return {"rows": rows, "summary": summary, "warnings": warnings}
