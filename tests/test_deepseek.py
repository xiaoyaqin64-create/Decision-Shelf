from __future__ import annotations

import json
import unittest

from decision_shelf.deepseek import AIService, DeepSeekClient, DeepSeekConfig
from decision_shelf.models import Candidate, Card, DecisionContext


def response(content) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class DeepSeekTestCase(unittest.TestCase):
    def test_valid_json_context_response(self) -> None:
        sent_payloads = []

        def transport(payload):
            sent_payloads.append(payload)
            return response(
                json.dumps(
                    {
                        "energy_level": "high",
                        "moods": ["被震撼"],
                        "preferences": ["科幻"],
                    },
                    ensure_ascii=False,
                )
            )

        client = DeepSeekClient(
            DeepSeekConfig(api_key="test"),
            transport=transport,
        )
        result = AIService(client).analyze_context("想看点震撼的科幻")
        self.assertEqual(result["source"], "deepseek")
        self.assertEqual(result["energy_level"], "high")
        self.assertEqual(result["preferences"], ["科幻"])
        self.assertEqual(sent_payloads[0]["thinking"], {"type": "disabled"})

    def test_empty_content_is_retried_and_then_succeeds(self) -> None:
        calls = []

        def transport(payload):
            calls.append(payload["messages"][-1]["content"])
            if len(calls) == 1:
                return response("")
            return response('{"energy_level":"medium","moods":[],"preferences":[]}')

        client = DeepSeekClient(
            DeepSeekConfig(api_key="test", json_retries=1), transport=transport
        )
        result = AIService(client).analyze_context("状态还行")
        self.assertEqual(result["source"], "deepseek")
        self.assertEqual(len(calls), 2)
        self.assertIn("请重试", calls[1])

    def test_repeated_empty_content_has_readable_fallback_error(self) -> None:
        client = DeepSeekClient(
            DeepSeekConfig(api_key="test", json_retries=1),
            transport=lambda payload: response(""),
        )
        service = AIService(client)
        result = service.analyze_context("今天很累")
        self.assertEqual(result["source"], "local-fallback")
        self.assertIn("空 content", service.last_error)
        self.assertIn("共尝试 2 次", service.last_error)

    def test_missing_key_uses_local_fallback(self) -> None:
        service = AIService(DeepSeekClient(DeepSeekConfig(api_key="")))
        result = service.analyze_context("今天很累，想轻松一点")
        self.assertEqual(result["source"], "local-fallback")
        self.assertEqual(result["energy_level"], "low")
        self.assertIn("轻松", result["moods"])

    def test_timeout_uses_local_fallback(self) -> None:
        def timeout(_payload):
            raise TimeoutError("timed out")

        service = AIService(
            DeepSeekClient(DeepSeekConfig(api_key="test"), transport=timeout)
        )
        result = service.analyze_context("想获得灵感")
        self.assertEqual(result["source"], "local-fallback")
        self.assertTrue(any(item in result["preferences"] for item in ("获得灵感", "灵感")))

    def test_invalid_json_uses_template_explanation(self) -> None:
        client = DeepSeekClient(
            DeepSeekConfig(api_key="test"),
            transport=lambda payload: response("not-json"),
        )
        service = AIService(client)
        card = Card(
            id="movie",
            category="movie",
            title="测试电影",
            duration_minutes=90,
            tags=["科幻"],
            mood_fit=["被震撼"],
        )
        candidate = Candidate(
            card=card,
            total_score=80,
            fit_score=75,
            scores={"energy": 20},
        )
        context = DecisionContext(
            available_minutes=120,
            energy_level="medium",
            categories=["movie"],
            preferences=["科幻"],
            moods=["被震撼"],
        )
        service.explain_candidates([candidate], context)
        self.assertTrue(candidate.explanation)
        self.assertIn("120", candidate.explanation)
        self.assertIsNotNone(service.last_error)

    def test_explanation_only_applies_to_primary_candidate(self) -> None:
        payload_result = {
            "explanations": [
                {"id": "b", "reason": "第二条理由"},
                {"id": "a", "reason": "第一条理由"},
            ]
        }
        client = DeepSeekClient(
            DeepSeekConfig(api_key="test"),
            transport=lambda payload: response(json.dumps(payload_result, ensure_ascii=False)),
        )
        service = AIService(client)
        candidates = [
            Candidate(Card("a", "album", "A", duration_minutes=30), 90, 80, {}),
            Candidate(Card("b", "album", "B", duration_minutes=30), 80, 70, {}),
        ]
        context = DecisionContext(60, "medium", ["album"])
        service.explain_candidates(candidates, context)
        self.assertEqual([item.card.id for item in candidates], ["a", "b"])
        self.assertEqual(candidates[0].explanation, "第一条理由")
        self.assertEqual(candidates[1].explanation, "")

    def test_unverified_description_is_conservative_and_auditable(self) -> None:
        description = "这是一部围绕个人选择与内心变化展开的作品，整体侧重情绪体验、关系观察与成长思考，适合希望从内容中获得共鸣与余味的人。"
        payload = {"tags": [], "mood_fit": [], "energy_level": "medium", "description": description, "mode": "unverified", "basis": []}
        service = AIService(DeepSeekClient(DeepSeekConfig(api_key="test"), transport=lambda _: response(json.dumps(payload, ensure_ascii=False))))
        result = service.suggest_card_metadata(Card("manual", "book", "未知作品"))
        self.assertEqual(result["description"], description)
        self.assertEqual(result["description_mode"], "unverified")
        self.assertEqual(result["description_basis"], [])

    def test_evidence_description_rejects_unknown_basis(self) -> None:
        valid_description = "这部作品依据已核验的作者与出版信息进行概述，聚焦作品的基本定位与阅读方向，不额外扩展未提供的人物、事件或具体情节。"
        responses = iter([
            {"description": valid_description, "mode": "evidence", "basis": ["publisher"], "tags": [], "mood_fit": []},
            {"description": valid_description, "mode": "evidence", "basis": ["author"], "tags": [], "mood_fit": []},
        ])
        service = AIService(DeepSeekClient(DeepSeekConfig(api_key="test"), transport=lambda _: response(json.dumps(next(responses), ensure_ascii=False))))
        card = Card("verified", "book", "有依据作品", source="openlibrary", external_id="OL1W", extension={"author": "某作者"})
        result = service.suggest_card_metadata(card)
        self.assertEqual(result["description_mode"], "evidence")
        self.assertEqual(result["description_basis"], ["author"])
        self.assertTrue(result["retried"])

    def test_existing_description_is_never_replaced(self) -> None:
        payload = {"tags": ["科幻"], "mood_fit": [], "energy_level": "medium", "description": "模型试图覆盖", "mode": "none", "basis": []}
        service = AIService(DeepSeekClient(DeepSeekConfig(api_key="test"), transport=lambda _: response(json.dumps(payload, ensure_ascii=False))))
        result = service.suggest_card_metadata(Card("existing", "movie", "已有简介", description="保留这段简介"))
        self.assertEqual(result["description"], "")
        self.assertEqual(result["description_mode"], "none")


if __name__ == "__main__":
    unittest.main()
