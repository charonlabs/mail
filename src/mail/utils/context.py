from functools import lru_cache

import litellm


@lru_cache(maxsize=1000)
def get_model_ctx_len(llm: str) -> int:
    """
    Get the context length of a model from the LiteLLM model cost map.
    """
    item = litellm.model_cost.get(llm)
    if item is None:
        _, slug = llm.split("/")
        item = litellm.model_cost.get(slug)
    if item is None:
        return 0
    return item.get("max_input_tokens", 0)
