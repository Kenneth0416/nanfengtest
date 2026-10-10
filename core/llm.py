"""Model calls made from Python tools: short text (brief headline, setup proposals), JSON
(classification) and page images (PDF reading). The agent loop itself runs in Pi (pi_engine/).
With no key these tools use their rule-based paths.
"""
from __future__ import annotations

import json
import os
import re


def _parse_json(text: str):
    m = re.search(r"\{.*\}|\[.*\]", text, flags=re.S)
    return json.loads(m.group(0)) if m else None


def _b64(png: bytes) -> str:
    import base64
    return base64.standard_b64encode(png).decode()


def _kind(data: bytes) -> str:
    return "jpeg" if data[:3] == b"\xff\xd8\xff" else "webp" if data[8:12] == b"WEBP" else "png"


class OfflineLLM:
    name = "offline"
    model = "none (rule-based tools)"
    available = False

    def complete_json(self, prompt: str):
        raise RuntimeError("No LLM configured")

    def complete_json_images(self, prompt: str, images: list[bytes]):
        raise RuntimeError("No LLM configured")


class AnthropicLLM:
    name = "anthropic"
    available = True

    def __init__(self, model: str, effort: str = "medium"):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def _create(self, effort=None, **kw):
        # Server-side fallback re-runs a declined request on a fallback model.
        return self.client.beta.messages.create(
            model=self.model, max_tokens=16000,
            output_config={"effort": effort or self.effort},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)

    def complete(self, prompt: str, system: str = "") -> str:
        kw = {"system": system} if system else {}
        resp = self._create(effort="low", messages=[{"role": "user", "content": prompt}], **kw)
        return "\n".join(b.text for b in resp.content if b.type == "text")

    def complete_json(self, prompt: str):
        return _parse_json(self.complete(prompt + "\n\nRespond with JSON only."))

    def complete_json_images(self, prompt: str, images: list[bytes]):
        """Page images (PNG) plus an instruction; returns parsed JSON."""
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(png)}}
                   for png in images]
        content.append({"type": "text", "text": prompt + "\n\nRespond with JSON only."})
        resp = self._create(effort="low", messages=[{"role": "user", "content": content}])
        return _parse_json("\n".join(b.text for b in resp.content if b.type == "text"))


class OpenAILLM:
    name = "openai"
    available = True

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None, name: str = "openai"):
        import openai
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url) if api_key else openai.OpenAI()
        self.model = model
        self.name = name

    def complete(self, prompt: str, system: str = "") -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        resp = self.client.chat.completions.create(model=self.model, messages=msgs)
        return resp.choices[0].message.content or ""

    def complete_json(self, prompt: str):
        return _parse_json(self.complete(prompt + "\n\nRespond with JSON only."))

    def complete_json_images(self, prompt: str, images: list[bytes]):
        content = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64(png)}"}} for png in images]
        content.append({"type": "text", "text": prompt + "\n\nRespond with JSON only."})
        resp = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": content}])
        return _parse_json(resp.choices[0].message.content or "")


FIGURES_SCHEMA = {  # json_schema for vision extraction; the root has to be an object
    "name": "figures", "strict": True,
    "schema": {"type": "object", "additionalProperties": False, "required": ["figures"], "properties": {
        "figures": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["market_text", "metric", "value", "page", "where", "label_status", "evidence"],
            "properties": {"market_text": {"type": "string"}, "metric": {"type": "string"},
                           "value": {"type": "number"}, "page": {"type": "integer"}, "where": {"type": "string"},
                           "label_status": {"type": "string", "enum": ["explicit", "inferred"]},
                           "evidence": {"type": "string"}}}}}}}


class VisionLLM:
    """An OpenAI-compatible vision model used only to read PDF pages (e.g. Xiaomi MiMo-V2.6-Flash)."""
    available = True
    name = "vision"

    def __init__(self, cfg: dict, api_key: str):
        import openai
        self.client = openai.OpenAI(api_key=api_key, base_url=os.getenv("VISION_BASE_URL", cfg.get("base_url")))
        self.model = os.getenv("VISION_MODEL", cfg.get("model", "mimo-v2.6-flash"))
        self.detail = cfg.get("detail", "high")
        self.reasoning = cfg.get("reasoning_effort", "low")   # reading a table needs no long chain of thought
        self.max_tokens = int(cfg.get("max_tokens", 8000))     # one page batch is a few hundred tokens of JSON
        self.pages_per_call = int(cfg.get("pages_per_call", 2))
        self.long_side = int(cfg.get("long_side_px", 2500))
        self.parallel = int(cfg.get("parallel", 4))
        self.use_schema = True

    def _content(self, prompt: str, images: list[bytes]):
        content = [{"type": "image_url", "image_url": {"url": f"data:image/{_kind(png)};base64,{_b64(png)}",
                                                       "detail": self.detail}} for png in images]
        content.append({"type": "text", "text": prompt})
        return content

    def complete_json_images(self, prompt: str, images: list[bytes]):
        """PDF pages -> the figures list (json_schema when the endpoint supports it)."""
        content = self._content(prompt + "\n\nReturn {\"figures\": [...]}.", images)
        kw = {"max_tokens": self.max_tokens, **({"reasoning_effort": self.reasoning} if self.reasoning else {})}
        if self.use_schema:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=[{"role": "user", "content": content}],
                    response_format={"type": "json_schema", "json_schema": FIGURES_SCHEMA}, **kw)
            except Exception as e:  # endpoint without json_schema support: plain JSON from now on
                if "response_format" not in str(e) and "json_schema" not in str(e):
                    raise
                self.use_schema = False
        if not self.use_schema:
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": content}], **kw)
        out = _parse_json(resp.choices[0].message.content or "")
        return out.get("figures", []) if isinstance(out, dict) else out

    def read_json_images(self, prompt: str, images: list[bytes]):
        """Any image (a photo, a screenshot, a rendered page) plus an instruction -> the JSON the prompt asks for."""
        kw = {"max_tokens": self.max_tokens, **({"reasoning_effort": self.reasoning} if self.reasoning else {})}
        resp = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": self._content(prompt + "\n\nRespond with JSON only.", images)}],
            **kw)
        return _parse_json(resp.choices[0].message.content or "")


def get_vision(cfg: dict, llm):
    """The PDF reader: the configured vision model if its key is set, else the chat model."""
    key = os.getenv(cfg.get("api_key_env", "MIMO_API_KEY"), "")
    if key and cfg.get("model"):
        try:
            return VisionLLM(cfg, key)
        except Exception as e:
            print(f"[llm] vision model unavailable ({e}); PDFs use the chat model")
    return llm


def get_llm(cfg: dict):
    """Pick a provider from config; 'auto' uses whichever API key is set."""
    provider = os.getenv("LLM_PROVIDER", cfg.get("provider", "auto")).lower()
    if provider == "auto":
        provider = ("mimo" if os.getenv("MIMO_API_KEY") else "anthropic" if os.getenv("ANTHROPIC_API_KEY")
                    else "openai" if os.getenv("OPENAI_API_KEY") else "offline")
    try:
        if provider == "mimo":  # Xiaomi MiMo through its OpenAI-compatible API (the project default)
            return OpenAILLM(os.getenv("MIMO_MODEL", cfg.get("mimo_model", "mimo-v2.6-flash")),
                             os.getenv("MIMO_API_KEY"), cfg.get("mimo_base_url", "https://api.xiaomimimo.com/v1"), "mimo")
        if provider == "anthropic":
            return AnthropicLLM(os.getenv("ANTHROPIC_MODEL", cfg.get("anthropic_model", "claude-opus-5-5")),
                                cfg.get("anthropic_effort", "medium"))
        if provider == "openai":
            return OpenAILLM(os.getenv("OPENAI_MODEL", cfg.get("openai_model", "gpt-5.5")))
    except Exception as e:  # missing package or bad key: keep the app usable
        print(f"[llm] {provider} unavailable ({e}); falling back to offline mode")
    return OfflineLLM()
