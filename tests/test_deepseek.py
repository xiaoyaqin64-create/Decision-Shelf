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


if __name__ == "__main__":
    unittest.main()
