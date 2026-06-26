from __future__ import annotations
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from pool_manager.endpoint_state import EndpointState
from pool_manager.scheduler import AllEndpointsExhausted, LLMScheduler

from pathlib import Path
import yaml
import os


def build_endpoints(config: str | Path, temperature: float = 0.0) -> list[EndpointState]:
    """
    config shape, per provider:
        {
            "models": [...],
            "keys": [...],
            "base_url": "...",        # optional
            "rpm_limit": int,         # required — requests/minute for this provider's models
            "rpd_limit": int,         # required — requests/day for this provider's models
        }
    """
    endpoints: list[EndpointState] = []

    with open(config) as f:
        config = yaml.safe_load(f)

    for provider, params in config.items():
        if "rpm_limit" not in params or "rpd_limit" not in params:
            raise ValueError(
                f"llm_config['{provider}'] is missing rpm_limit/rpd_limit — "
                "EndpointState requires both. Add the provider's published "
                "per-key rate limits."
            )

        rpm_limit = params["rpm_limit"]
        rpd_limit = params["rpd_limit"]

        for key in params["keys"]:
            api_key = os.environ.get(key)
            if not api_key:
                raise ValueError(
                    f"Environment variable '{key}' is not set"
                )
            for model in params["models"]:
                client_kwargs: Dict[str, Any] = {
                    "model": model,
                    "api_key": api_key,
                    "temperature": temperature,
                }
                if params.get("base_url"):
                    client_kwargs["base_url"] = params["base_url"]

                endpoints.append(
                    EndpointState(
                        id=f"{provider}:{model}:{key}",
                        provider=provider,
                        model=model,
                        rpm_limit=rpm_limit,
                        rpd_limit=rpd_limit,
                        client=ChatOpenAI(**client_kwargs),
                    )
                )

    return endpoints


class MultiProviderChatLLM(BaseChatModel):
    scheduler: LLMScheduler

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "multi_provider_chat"

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        while True:
            async with self.scheduler.allocate_endpoint() as ep:
                try:
                    call_kwargs = dict(kwargs)
                    if stop is not None:
                        call_kwargs["stop"] = stop

                    response = await ep.client.ainvoke(messages, **call_kwargs)

                    return ChatResult(
                        generations=[
                            ChatGeneration(
                                message=AIMessage(
                                    content=response.content,
                                    response_metadata=getattr(response, "response_metadata", {}),
                                    usage_metadata=getattr(response, "usage_metadata", None),
                                )
                            )
                        ]
                    )

                except RateLimitError:
                    ep.mark_rate_limited()
                    continue

                except Exception:
                    raise

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise NotImplementedError(
            "MultiProviderChatLLM is async-only — use ainvoke()/abatch(), "
            "not invoke()/batch()."
        )


def get_llm(
    config: str | Path,
    temperature: float = 0.0,
    max_wait_seconds: float = 120.0,
) -> MultiProviderChatLLM:
    endpoints = build_endpoints(config, temperature=temperature)
    scheduler = LLMScheduler(endpoints, max_wait_seconds=max_wait_seconds)
    return MultiProviderChatLLM(scheduler=scheduler)