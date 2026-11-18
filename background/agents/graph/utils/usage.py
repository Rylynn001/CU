"""读取模型实际返回的用量；不估算、不累加重复携带的历史。"""


def read_model_usage(response, model_name):
    usage = getattr(response, 'usage', None)
    if usage is None:
        return None

    def tokens(source, name):
        value = getattr(source, name, None)
        return value if isinstance(value, int) else None

    input_tokens = tokens(usage, 'prompt_tokens')
    output_tokens = tokens(usage, 'completion_tokens')
    total_tokens = tokens(usage, 'total_tokens')
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        'model': model_name, 'max_tokens': None, 'used_tokens': total_tokens,
        'input_tokens': input_tokens, 'output_tokens': output_tokens,
        'reasoning_tokens': tokens(getattr(usage, 'completion_tokens_details', None), 'reasoning_tokens'),
        'cached_tokens': tokens(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens'),
    }
