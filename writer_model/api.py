"""Stable import API for Xgrowth and other local callers."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from writer_model import settings
from writer_model.core import generate_final, load_editor
from writer_model.usage_log import UsageLogger


@dataclass
class EditResult:
    id: str | None
    source: str
    run_id: str | None
    artifact_type: str | None
    model_base: str
    adapter: str
    context: str
    draft: str
    outputs: list[str]
    chosen_output: str | None
    final_used_output: str | None = None
    accepted: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class WriterEditor:
    """Lazy-loading wrapper around the local SFT editor adapter."""

    def __init__(
        self,
        adapter_path=None,
        base_model=None,
        usage_path=None,
        log_usage=True,
    ):
        self.adapter_path = Path(adapter_path or settings.DEFAULT_ADAPTER)
        self.base_model = base_model or settings.BASE_MODEL
        self.log_usage = log_usage
        self.usage_logger = UsageLogger(usage_path)
        self._model = None
        self._tokenizer = None

    def load(self):
        if self._model is None or self._tokenizer is None:
            if not self.adapter_path.exists():
                raise FileNotFoundError(f"adapter not found: {self.adapter_path}")
            self._model, self._tokenizer = load_editor(
                adapter_path=self.adapter_path,
                base_model=self.base_model,
            )
        return self._model, self._tokenizer

    def edit(
        self,
        context,
        draft,
        *,
        n=1,
        temp=0.7,
        max_tokens=160,
        source="manual",
        run_id=None,
        artifact_type=None,
        metadata=None,
        log_usage=None,
    ):
        model, tokenizer = self.load()
        outputs = generate_final(
            model,
            tokenizer,
            context=context,
            draft=draft,
            n=max(1, int(n)),
            temp=temp,
            max_tokens=max_tokens,
        )
        result = EditResult(
            id=None,
            source=source,
            run_id=run_id,
            artifact_type=artifact_type,
            model_base=self.base_model,
            adapter=str(self.adapter_path),
            context=context,
            draft=draft,
            outputs=outputs,
            chosen_output=outputs[0] if outputs else None,
            metadata=metadata or {},
        )

        should_log = self.log_usage if log_usage is None else log_usage
        if should_log:
            row = self.usage_logger.append(result.to_dict())
            result.id = row["id"]
        return result


def edit(context, draft, **kwargs):
    """One-shot convenience helper.

    For repeated calls, instantiate WriterEditor once so the model stays loaded.
    """
    return WriterEditor(
        adapter_path=kwargs.pop("adapter_path", None),
        base_model=kwargs.pop("base_model", None),
        usage_path=kwargs.pop("usage_path", None),
        log_usage=kwargs.pop("log_usage", True),
    ).edit(context, draft, **kwargs)
