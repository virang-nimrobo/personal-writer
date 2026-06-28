"""Core MLX editor runtime.

This is the package-owned serving path. Legacy scripts import these functions so
training, eval, CLI, and Xgrowth all use the same generation behavior.
"""

from writer_model import settings
from writer_model.prompts import EDITOR_SYSTEM, build_user_prompt


def load_editor(adapter_path=None, base_model=None):
    from mlx_lm import load

    base = base_model or settings.BASE_MODEL
    kw = {"adapter_path": str(adapter_path)} if adapter_path else {}
    model, tokenizer = load(base, **kw)
    return model, tokenizer


def _generate(model, tokenizer, prompt, max_tokens, temp):
    from mlx_lm import generate

    # mlx_lm has changed sampler kwargs across versions. Keep compatibility with
    # both the newer sampler object and the older temp kwarg.
    try:
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=temp)
        return generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            verbose=False,
        )
    except (ImportError, TypeError):
        try:
            return generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temp,
                verbose=False,
            )
        except TypeError:
            return generate(model, tokenizer, prompt, max_tokens=max_tokens)


def generate_final(model, tokenizer, context, draft, n=1, temp=0.7, max_tokens=160):
    """Return n candidate final pieces for one {context, draft}."""
    messages = [
        {"role": "system", "content": EDITOR_SYSTEM},
        {"role": "user", "content": build_user_prompt(context, draft)},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    outs = []
    for i in range(n):
        # First candidate is stable; later candidates can explore.
        t = 0.0 if (n == 1 or i == 0) else temp
        outs.append(_generate(model, tokenizer, prompt, max_tokens, t).strip())
    return outs
