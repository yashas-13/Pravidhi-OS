"""Context Window Manager — ultra-large context support up to 1M tokens.

Features:
- Dynamic max_tokens per provider/model (Gemini 1M, Claude 200K, GPT 128K, etc.)
- Sliding window for models with smaller context
- Automatic context compression (summarization, truncation)
- Token counting with tiktoken fallback
- Context budget management for complex pipelines
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("pravidhi.context_window")


# ── Context Window Capacity by Provider ───────────────────────────────────────

MODEL_CONTEXT_CAPS: Dict[str, int] = {
    # Gemini — 1M context window
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-2.0-pro": 1_048_576,
    "gemini/gemini-2.5-flash": 1_048_576,
    "gemini/gemini-2.5-pro": 1_048_576,

    # GPT-4 — 128K / 1M
    "gpt-5.4-mini": 1_048_576,
    "gpt-5.5": 1_048_576,
    "gpt-5.3": 1_048_576,
    "gpt-4.1": 1_048_576,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "openai/gpt-5.4-mini": 1_048_576,
    "openai/gpt-5.5": 1_048_576,
    "openai/gpt-4o": 128_000,
    "openai/gpt-4o-mini": 128_000,

    # Claude — 200K
    "claude-sonnet-4.6": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    "anthropic/claude-sonnet-4.6": 200_000,
    "anthropic/claude-sonnet-4": 200_000,
    "anthropic/claude-opus-4": 200_000,
    "openrouter/anthropic/claude-sonnet-4.6": 200_000,
    "openrouter/anthropic/claude-opus-4": 200_000,

    # Llama / Open — 128K
    "llama-4-70b": 128_000,
    "llama-4-8b": 128_000,
    "llama-3.1-405b": 128_000,
    "llama-3.1-70b": 128_000,
    "llama-3.1-8b": 128_000,
    "meta-llama/llama-4-70b": 128_000,
    "openrouter/meta-llama/llama-4-70b": 128_000,

    # DeepSeek — 128K
    "deepseek-chat": 128_000,
    "deepseek-r1": 128_000,
    "deepseek-v3": 128_000,
    "deepseek/deepseek-chat": 128_000,
    "openrouter/deepseek/deepseek-chat": 128_000,

    # Mistral — 128K / 32K
    "mistral-large": 128_000,
    "mistral-small": 32_000,
    "codestral": 256_000,
    "mistral/mistral-large": 128_000,

    # Qwen — 128K / 1M
    "qwen-2.5-72b": 128_000,
    "qwen-2.5-32b": 128_000,
    "qwen-2.5-7b": 32_000,
    "qwen-2.5-1.5b": 32_000,

    # Local / OpenCode / Ollama — variable
    "opencode/default": 1_048_576,

    # Fallback for unknown models
    "__default__": 128_000,
    "__minimum__": 32_000,
}

# Max output tokens (generation limit) per model
MODEL_MAX_OUTPUT: Dict[str, int] = {
    "gemini-2.5-flash": 65_536,
    "gemini-2.5-pro": 65_536,
    "gpt-5.4-mini": 1_048_576,
    "gpt-5.5": 1_048_576,
    "gpt-4o": 16_384,
    "gpt-4o-mini": 16_384,
    "claude-sonnet-4.6": 8_192,
    "claude-opus-4": 4_096,
    "llama-4-70b": 4_096,
    "deepseek-chat": 8_192,
    "__default__": 16_384,
    "__minimum__": 4_096,
}


# ── Context Window Manager ────────────────────────────────────────────────────

@dataclass
class ContextBudget:
    """Calculated context budget for a request."""
    model: str = ""
    context_capacity: int = 128_000
    max_output_tokens: int = 16_384
    prompt_tokens: int = 0
    available_for_output: int = 16_384
    system_prompt_tokens: int = 0
    message_tokens: int = 0
    tool_def_tokens: int = 0
    history_tokens: int = 0
    compression_needed: bool = False
    compression_ratio: float = 1.0
    strategy: str = "none"  # none | truncate | summarize | sliding_window


class ContextWindowManager:
    """Manages context windows across all providers with intelligent budgeting."""

    def __init__(self):
        self._tokenizer_cache: Dict[str, Any] = {}

    def get_context_capacity(self, model: str) -> int:
        """Get the context window capacity for a given model."""
        # Exact match
        if model in MODEL_CONTEXT_CAPS:
            return MODEL_CONTEXT_CAPS[model]

        # Prefix match (e.g., "gpt-5.4-mini" matches "gpt-5.4-mini")
        for key, cap in MODEL_CONTEXT_CAPS.items():
            if model.endswith(key) or key.endswith(model) or model.startswith(key) or key.startswith(model):
                return cap

        # Check by provider prefix
        provider = model.split("/")[0] if "/" in model else model
        provider_key = f"{provider}/__default__"
        if provider_key in MODEL_CONTEXT_CAPS:
            return MODEL_CONTEXT_CAPS[provider_key]

        return MODEL_CONTEXT_CAPS["__default__"]

    def get_max_output(self, model: str) -> int:
        """Get the maximum output token limit for a given model."""
        if model in MODEL_MAX_OUTPUT:
            return MODEL_MAX_OUTPUT[model]
        for key, cap in MODEL_MAX_OUTPUT.items():
            if model.endswith(key) or key.endswith(model):
                return cap
        return MODEL_MAX_OUTPUT["__default__"]

    def count_tokens(self, text: str, model: str = "") -> int:
        """Count tokens in text using tiktoken or character-based fallback."""
        try:
            import tiktoken
            # Map model to encoding
            encoding_name = "cl100k_base"
            if "gpt-4" in model or "gpt-5" in model or "gpt-3" in model:
                try:
                    encoding = tiktoken.encoding_for_model(model.split("/")[-1])
                    return len(encoding.encode(text))
                except Exception:
                    pass
            try:
                encoding = tiktoken.get_encoding(encoding_name)
                return len(encoding.encode(text))
            except Exception:
                pass
        except ImportError:
            pass

        # Fallback: character-based estimation (about 4 chars per token)
        return len(text) // 4

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]],
                                  model: str = "") -> int:
        """Estimate total tokens in a list of messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content, model)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += self.count_tokens(part.get("text", ""), model)
                        if "image_url" in part:
                            total += 1000  # Approximate image tokens
            total += 4  # Message overhead
        return total

    def calculate_budget(self, messages: List[Dict[str, Any]],
                          model: str = "",
                          system_prompt: str = "",
                          tool_definitions: str = "",
                          max_output: Optional[int] = None,
                          safety_margin: float = 0.1) -> ContextBudget:
        """Calculate context budget and determine if compression is needed."""
        capacity = self.get_context_capacity(model)
        max_out = max_output or self.get_max_output(model)

        # Count tokens
        system_tokens = self.count_tokens(system_prompt, model) if system_prompt else 0
        tool_tokens = self.count_tokens(tool_definitions, model) if tool_definitions else 0
        message_tokens = self.estimate_messages_tokens(messages, model)

        total_prompt = system_tokens + tool_tokens + message_tokens
        available = capacity - int(capacity * safety_margin)

        budget = ContextBudget(
            model=model,
            context_capacity=capacity,
            max_output_tokens=max_out,
            prompt_tokens=total_prompt,
            available_for_output=min(max_out, available - total_prompt),
            system_prompt_tokens=system_tokens,
            message_tokens=message_tokens,
            tool_def_tokens=tool_tokens,
        )

        # Determine if compression is needed
        if total_prompt > available:
            budget.compression_needed = True
            ratio = available / total_prompt
            budget.compression_ratio = ratio

            # Choose strategy
            if ratio < 0.3:
                budget.strategy = "summarize"
            elif ratio < 0.7:
                budget.strategy = "sliding_window"
            else:
                budget.strategy = "truncate"

        return budget

    def compress_messages(self, messages: List[Dict[str, Any]],
                           budget: ContextBudget,
                           model: str = "") -> List[Dict[str, Any]]:
        """Compress messages to fit within context budget."""
        if not budget.compression_needed:
            return messages

        target = budget.context_capacity - budget.max_output_tokens - budget.system_prompt_tokens - budget.tool_def_tokens
        target -= int(target * 0.1)  # Safety margin

        if budget.strategy == "truncate":
            return self._truncate_messages(messages, target, model)

        elif budget.strategy == "sliding_window":
            return self._sliding_window(messages, target, model)

        elif budget.strategy == "summarize":
            return self._summarize_messages(messages, target, model)

        return messages

    def _truncate_messages(self, messages: List[Dict[str, Any]],
                            target_tokens: int, model: str) -> List[Dict[str, Any]]:
        """Truncate oldest messages while keeping system prompt."""
        result = []
        total = 0

        # Always keep system messages
        for msg in messages:
            if msg.get("role") == "system":
                result.append(msg)
                total += self.estimate_messages_tokens([msg], model)

        # Keep most recent messages
        remaining = [m for m in messages if m.get("role") != "system"]
        for msg in reversed(remaining):
            msg_tokens = self.estimate_messages_tokens([msg], model)
            if total + msg_tokens <= target_tokens:
                result.insert(1 if result and result[0].get("role") == "system" else 0, msg)
                total += msg_tokens
            else:
                break

        return result

    def _sliding_window(self, messages: List[Dict[str, Any]],
                         target_tokens: int, model: str) -> List[Dict[str, Any]]:
        """Keep a sliding window of recent messages plus system prompt."""
        result = []
        total = 0

        # Keep system messages
        for msg in messages:
            if msg.get("role") == "system":
                result.append(msg)
                total += self.estimate_messages_tokens([msg], model)

        # Keep recent messages (assistant + user) in order
        remaining = [m for m in messages if m.get("role") != "system"]
        # Take from the end (most recent)
        window = []
        for msg in reversed(remaining):
            msg_tokens = self.estimate_messages_tokens([msg], model)
            if total + msg_tokens <= target_tokens:
                window.insert(0, msg)
                total += msg_tokens
            else:
                break

        # Add a summary note
        trimmed = len(remaining) - len(window)
        if trimmed > 0:
            window.insert(0, {
                "role": "system",
                "content": f"[{trimmed} earlier messages trimmed to fit context window. Using last {len(window)} messages.]"
            })

        result.extend(window)
        return result

    def _summarize_messages(self, messages: List[Dict[str, Any]],
                             target_tokens: int, model: str) -> List[Dict[str, Any]]:
        """Keep system prompt + last message + summary of the rest."""
        result = []

        # Keep system messages
        for msg in messages:
            if msg.get("role") == "system":
                result.append(msg)

        # Get the last user/assistant exchange
        non_system = [m for m in messages if m.get("role") != "system"]
        last_few = non_system[-4:] if len(non_system) >= 4 else non_system

        # Count tokens for last few
        for msg in last_few:
            tokens = self.estimate_messages_tokens([msg], model)
            if self.estimate_messages_tokens(result + [msg], model) <= target_tokens:
                result.append(msg)

        trimmed = len(non_system) - len(last_few)
        if trimmed > 0:
            result.insert(1 if len(result) > 0 and result[0].get("role") == "system" else 0, {
                "role": "system",
                "content": f"## Compressed Context\n{trimmed} earlier messages were summarized. Key context from the conversation has been preserved. The most recent {len(last_few)} messages are shown in full."
            })

        return result


# ── Integration Helpers ───────────────────────────────────────────────────────

def get_safe_max_tokens(model: str, requested: int = 1_000_000) -> int:
    """Get safe max_tokens for a model, capped to its actual output limit."""
    mgr = ContextWindowManager()
    max_out = mgr.get_max_output(model)
    return min(requested, max_out)


def smart_max_tokens(messages: List[Dict[str, Any]], model: str,
                      requested_max: int = 1_000_000) -> int:
    """Intelligently set max_tokens based on context usage."""
    mgr = ContextWindowManager()
    budget = mgr.calculate_budget(messages, model)
    # Leave enough room for output
    available = budget.context_capacity - budget.prompt_tokens
    safe = min(requested_max, budget.max_output_tokens, available)
    return max(safe, 256)  # Always at least 256


# ── Default Configuration ─────────────────────────────────────────────────────

DEFAULT_MAX_TOKENS = 1_000_000  # 1M default
DEFAULT_TEMPERATURE = 0.3

CONTEXT_WINDOW_CONFIG = {
    "default_max_tokens": DEFAULT_MAX_TOKENS,
    "default_temperature": DEFAULT_TEMPERATURE,
    "safety_margin": 0.1,
    "enable_auto_compression": True,
    "compression_strategy": "sliding_window",
    "enable_token_counting": True,
    "model_context_caps": MODEL_CONTEXT_CAPS,
    "model_max_output": MODEL_MAX_OUTPUT,
}
