import json
from pathlib import Path
from unittest.mock import MagicMock
from app.agent.hypotheses import format_investigation_prompt, generate_hypotheses
from app.agent.llm import LLMClient, parse_json_response, strip_json_markdown

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_strip_json_markdown():
    wrapped = "```json\n{\"test\": 123}\n```"
    assert strip_json_markdown(wrapped) == "{\"test\": 123}"

    unwrapped = "{\"test\": 123}"
    assert strip_json_markdown(unwrapped) == "{\"test\": 123}"


def test_format_investigation_prompt():
    fixture_path = FIXTURES_DIR / "db_errors.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    prompt = format_investigation_prompt(evidence)
    assert "checkout" in prompt
    assert "error_ratio" in prompt
    assert "db" in prompt


def test_generate_hypotheses_mock():
    fixture_path = FIXTURES_DIR / "db_errors.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    mock_client = MagicMock(spec=LLMClient)
    mock_client.complete.return_value = {
        "role": "assistant",
        "content": json.dumps({
            "hypotheses": [
                {
                    "rank": 1,
                    "root_cause_service": "db",
                    "summary": "Database service is throwing 500 internal errors",
                    "confidence": 0.95,
                    "evidence": [
                        "Error logs show 'injected fault: internal error'",
                        "No dependencies of db are unhealthy"
                    ]
                }
            ]
        })
    }

    result = generate_hypotheses(evidence, client=mock_client)
    assert "hypotheses" in result
    hyp = result["hypotheses"][0]
    assert hyp["root_cause_service"] == "db"
    assert hyp["rank"] == 1
    assert len(hyp["evidence"]) == 2
