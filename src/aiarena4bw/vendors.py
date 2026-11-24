"""Anbieter (Hersteller) eines Modells, abgeleitet aus der Modell-ID.

Plattform = eingerichteter Zugang (openrouter, sapaicore, …); Anbieter = Unternehmen hinter dem
Modell. OpenRouter-IDs beginnen mit dem Anbieter ("anthropic/claude-…"), SAP-AI-Core-IDs meist auch
("anthropic--claude-…"), andere nur mit dem Modellnamen ("gemini-2.5-pro").
"""

from __future__ import annotations

import re

NAMES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "qwen": "Qwen (Alibaba)",
    "alibaba": "Qwen (Alibaba)",
    "deepseek": "DeepSeek",
    "mistralai": "Mistral AI",
    "mistral": "Mistral AI",
    "z-ai": "Z.ai",
    "x-ai": "xAI",
    "xiaomi": "Xiaomi",
    "amazon": "Amazon",
    "cohere": "Cohere",
    "meta": "Meta",
    "meta-llama": "Meta",
    "moonshotai": "Moonshot AI",
    "minimax": "MiniMax",
    "nvidia": "NVIDIA",
    "bytedance-seed": "ByteDance",
    "perplexity": "Perplexity",
    "sap": "SAP",
    "ibm-granite": "IBM",
    "microsoft": "Microsoft",
    "tencent": "Tencent",
    "baidu": "Baidu",
    "unknown": "unbekannt",
}

_BY_NAME = [
    (r"^(gpt|o\d|chatgpt|text-embedding)", "openai"),
    (r"^(gemini|gemma)", "google"),
    (r"^claude", "anthropic"),
    (r"^(sonar|r1-)", "perplexity"),
    (r"^sap-", "sap"),
    (r"^(mistral|codestral|pixtral|magistral|devstral)", "mistralai"),
    (r"^llama", "meta"),
    (r"^(nova|titan)", "amazon"),
    (r"^(command|embed)", "cohere"),
    (r"^deepseek", "deepseek"),
    (r"^(qwen|qwq)", "qwen"),
    (r"^grok", "x-ai"),
    (r"^glm", "z-ai"),
    (r"^kimi", "moonshotai"),
    (r"^phi", "microsoft"),
]


def split_model_id(full_id: str) -> tuple[str, str]:
    """'openrouter:qwen/x:free' -> ('openrouter', 'qwen/x:free'). Ohne Plattform: ('', id)."""
    head, sep, tail = full_id.partition(":")
    if sep and "/" not in head and head:
        return head, tail
    return "", full_id


def vendor_key(model_id: str) -> str:
    """Kennung des Anbieters, z. B. 'anthropic'. model_id mit oder ohne Plattform."""
    mid = split_model_id(model_id)[1].strip().lower().lstrip("~")
    if "/" in mid:
        head = mid.split("/", 1)[0]
        if head not in ("models", "publishers", "lmstudio-community"):
            return head
        mid = mid.split("/")[-1]
    if "--" in mid:
        return mid.split("--", 1)[0]
    for pattern, key in _BY_NAME:
        if re.match(pattern, mid):
            return key
    return "unknown"


def vendor_name(key: str) -> str:
    return NAMES.get(key) or key.replace("-", " ").title()


def vendor_of(model_id: str) -> str:
    return vendor_name(vendor_key(model_id))


_VARIANT = re.compile(r":(thinking|batch|free|beta|extended|nitro|floor|exacto)$")


def model_key(model_id: str) -> frozenset[str]:
    """Namensteile eines Modells ohne Plattform, Anbieter, Variante und Reihenfolge.

    Damit gilt 'openrouter:anthropic/claude-opus-4.8' als dasselbe Modell wie
    'sapaicore:anthropic--claude-4.8-opus' oder 'anthropic:claude-opus-4-8'.
    """
    name = split_model_id(str(model_id))[1].lower()
    name = _VARIANT.sub("", name).split("/")[-1]
    if "--" in name:
        name = name.split("--", 1)[1]
    name = re.sub(r"(?<=\d)[-_](?=\d)", ".", name)  # 4-8 -> 4.8
    name = re.sub(r"[-_.]20\d{6}$", "", name)  # Datumsanhang
    return frozenset(t for t in re.split(r"[-_\s]+", name) if t)


def same_model(a: str, b: str) -> bool:
    """Gleiche ID oder dasselbe Modell auf einer anderen Plattform."""
    if a == b:
        return True
    ka, kb = model_key(a), model_key(b)
    return bool(ka) and ka == kb
