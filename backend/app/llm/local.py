"""BO4 local Ollama adapter; no remote or billed fallback."""
import json
import time
import httpx
from .provider import LLMError, LLMResult


class LocalHermesProvider:
    def __init__(self, model: str = "hermes3:8b") -> None:
        self.model = model

    def complete(self, messages, *, max_tokens=3000, temperature=0.0, json_mode=True, tools=None, tool_choice=None):
        started = time.perf_counter()
        native_messages = []
        for source in messages:
            message = {"role": source["role"], "content": source.get("content") or ""}
            if source.get("tool_calls"):
                native_calls = []
                for source_call in source["tool_calls"]:
                    call = {"type": "function", "function": dict(source_call.get("function") or {})}
                    arguments = call["function"].get("arguments", {})
                    if isinstance(arguments, str):
                        try: arguments = json.loads(arguments)
                        except json.JSONDecodeError: arguments = {}
                    call["function"]["arguments"] = arguments
                    native_calls.append(call)
                message["tool_calls"] = native_calls
            native_messages.append(message)
        # Ollama's native endpoint accepts an explicit context size. Hermes was
        # otherwise started with 4K and crashed once schemas + tool evidence were
        # appended to the conversation.
        body = {"model": self.model, "messages": native_messages, "stream": False, "keep_alive": "10m",
                "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192}}
        if tools:
            body["tools"] = tools
        elif json_mode:
            body["format"] = "json"
        try:
            response = httpx.post("http://127.0.0.1:11434/api/chat", json=body, timeout=180)
            response.raise_for_status()
            data = response.json()
            if data.get("done_reason") == "length":
                raise LLMError("output_truncated", f"Ollama a atteint la limite de {max_tokens} jetons")
            message = data["message"]
            calls = message.get("tool_calls") or []
            for index, call in enumerate(calls):
                call.setdefault("id", f"local_call_{index}")
                call.setdefault("type", "function")
            content = message.get("content") or ""
            if not content.strip() and not calls: raise ValueError("empty response")
            usage = {"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0),
                     "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)}
            return LLMResult(content, self.model, data.get("model", self.model), time.perf_counter()-started,
                             usage=usage, model_used=self.model, tool_calls=calls)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("local_provider_error", f"Ollama: {type(exc).__name__}: {exc}") from exc
