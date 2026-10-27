import json
import re
from typing import Any, Dict, List, Optional, Union
import httpx
from app.config import settings


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 90.0,
    ):
        self.base_url = (base_url or settings.get_llm_url()).rstrip("/")
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.timeout = timeout

        if not self.base_url.endswith("/chat/completions"):
            self.endpoint = f"{self.base_url}/chat/completions"
        else:
            self.endpoint = self.base_url

    def complete(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        temp = temperature if temperature is not None else settings.llm_temperature
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
        }

        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(f"LLM API returned status {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise LLMError(f"Failed to connect to LLM at {self.endpoint}: {type(e).__name__}: {e}") from e

        choices = data.get("choices", [])
        if not choices:
            raise LLMError(f"LLM response contained no choices: {data}")

        return choices[0].get("message", {})


def strip_json_markdown(text: str) -> str:
    """Removes ```json ... ``` or ``` ... ``` fences from LLM responses."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


def parse_json_response(text: str) -> Union[Dict[str, Any], List[Any]]:
    cleaned = strip_json_markdown(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to decode JSON from model response: {e}\nRaw content:\n{text[:500]}") from e
