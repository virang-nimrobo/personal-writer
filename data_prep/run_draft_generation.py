#!/usr/bin/env python3
"""Run configured draft models to create draft output chunks.

This fills the same handoff shape used by manual model agents:

  data_prep/generation-*/<model>/inputs/000.input.jsonl
  data_prep/generation-*/<model>/outputs/000.output.jsonl

Each output row is exactly {"id": "...", "draft": "..."}.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "draft_models.json"
TEMPLATE = HERE / "templates" / "instruction.md"
DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_RAW_RESPONSE_DIRNAME = "_raw_responses"
DEFAULT_INVALID_ROW_DIRNAME = "_invalid_rows"
DEFAULT_RETRY_INPUT_DIRNAME = "_retry_inputs"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def load_config(path):
    config = json.loads(Path(path).read_text())
    models = config.get("models")
    if not isinstance(models, dict) or not models:
        sys.exit(f"{path}: expected non-empty object at key 'models'")
    for name, spec in models.items():
        backend = spec.get("backend", "openai-compatible")
        if backend not in {"openai-compatible", "mlx"}:
            sys.exit(f"{path}: model {name!r} has unsupported backend {backend!r}")
        required = ("model",) if backend == "mlx" else ("base_url", "model")
        missing = [key for key in required if not str(spec.get(key, "")).strip()]
        if missing:
            sys.exit(f"{path}: model {name!r} missing {', '.join(missing)}")
    return config


def infer_openai_spec(name, provider=None, base_url=None):
    provider = provider or "lmstudio"
    if provider in {"lmstudio", "lm-studio"}:
        resolved_base = base_url or DEFAULT_LMSTUDIO_BASE_URL
        label = "LM Studio"
    elif provider == "ollama":
        resolved_base = base_url or DEFAULT_OLLAMA_BASE_URL
        label = "Ollama"
    else:
        resolved_base = base_url
        label = provider
    if not resolved_base:
        sys.exit(f"--provider {provider!r} requires --base-url")
    return {
        "backend": "openai-compatible",
        "provider": f"{label} ({resolved_base})",
        "base_url": resolved_base,
        "model": name,
        "temperature": 0.8,
        "max_tokens": 220,
    }


def resolve_model(config, name, *, provider=None, base_url=None, mlx_model=None):
    if mlx_model:
        return {
            "backend": "mlx",
            "provider": "MLX local",
            "model": mlx_model,
            "temperature": 0.8,
            "max_tokens": 220,
        }

    models = config["models"]
    if name in models:
        spec = dict(models[name])
    else:
        spec = infer_openai_spec(name, provider=provider, base_url=base_url)

    if base_url and spec.get("backend", "openai-compatible") == "openai-compatible":
        spec["base_url"] = base_url

    if name not in models and not provider and not base_url:
        choices = ", ".join(sorted(models))
        sys.exit(
            f"unknown draft model {name!r}; configured models: {choices}. "
            "Pass --provider lmstudio|ollama or --base-url to run an ad hoc OpenAI-compatible model."
        )
    return spec


def generation_dir(args):
    if args.generation_dir:
        return args.generation_dir
    return HERE / f"generation-{args.generation_date}"


def input_indexes(inputs_dir):
    indexes = []
    for path in sorted(inputs_dir.glob("*.input.jsonl")):
        try:
            indexes.append(int(path.name.split(".", 1)[0]))
        except ValueError:
            continue
    return indexes


def selected_indexes(inputs_dir, start, end):
    indexes = input_indexes(inputs_dir)
    if not indexes:
        sys.exit(f"no input chunks found under {inputs_dir}")
    lo = min(indexes) if start is None else start
    hi = max(indexes) if end is None else end
    selected = [idx for idx in indexes if lo <= idx <= hi]
    if not selected:
        sys.exit(f"no input chunks found in range {lo:03d}..{hi:03d}")
    return selected


def build_user_prompt(rows):
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    return (
        "Generate exactly one off-voice draft for each input row below.\n"
        "Return JSONL only: one JSON object per line, with exactly id and draft.\n"
        "Preserve ids and row order exactly in proper JSONL format. Do not include special characters, markdown or commentary.\n\n"
        f"{payload}"
    )


def completion_endpoint(base_url):
    return base_url.rstrip("/") + "/chat/completions"


def ollama_endpoint(base_url):
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root + "/api/chat"


def is_ollama_spec(spec):
    provider = str(spec.get("provider", "")).lower()
    base_url = str(spec.get("base_url", "")).lower()
    return spec.get("api") == "ollama" or "ollama" in provider or ":11434" in base_url


def content_part_text(part):
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""
    for key in ("text", "content"):
        value = part.get(key)
        if isinstance(value, str):
            return value
    return ""


def first_choice(result):
    try:
        return result["choices"][0]
    except (KeyError, IndexError, TypeError):
        sys.exit("model response did not contain choices[0]")


def extract_message_content(result):
    choice = first_choice(result)
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        message = {}

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(content_part_text(part) for part in content)

    # Some local OpenAI-compatible servers expose generated text in alternate
    # fields, especially around reasoning/chat-template variants.
    for container in (message, choice):
        if not isinstance(container, dict):
            continue
        for key in ("text", "response", "output", "reasoning_content"):
            value = container.get(key)
            if isinstance(value, str):
                return value
    return ""


def parse_think(value):
    if value is None or value == "auto":
        return None
    return value == "on"


def reasoning_details(raw_response):
    choice = first_choice(raw_response)
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        message = {}
    reasoning = message.get("reasoning") or message.get("reasoning_content") or choice.get("reasoning")
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    if isinstance(reasoning, str) and reasoning.strip():
        return len(reasoning), finish_reason
    return 0, finish_reason


def call_chat_completion(spec, rows, instruction, *, temperature=None, max_tokens=None, timeout=120, think=None):
    resolved_think = parse_think(think if think is not None else spec.get("think"))
    if resolved_think is not None and is_ollama_spec(spec):
        return call_ollama_chat(
            spec,
            rows,
            instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            think=resolved_think,
        )

    payload = {
        "model": spec["model"],
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": build_user_prompt(rows)},
        ],
        "temperature": spec.get("temperature", 0.8) if temperature is None else temperature,
        "max_tokens": spec.get("max_tokens", 220) if max_tokens is None else max_tokens,
    }
    if resolved_think is not None:
        payload["think"] = resolved_think
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        completion_endpoint(spec["base_url"]),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        sys.exit(f"model request failed for {spec['model']} at {spec['base_url']}: {exc}")

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        sys.exit(f"model response was not JSON: {exc}")
    return extract_message_content(result), result


def call_ollama_chat(spec, rows, instruction, *, temperature=None, max_tokens=None, timeout=120, think=None):
    options = {
        "temperature": spec.get("temperature", 0.8) if temperature is None else temperature,
        "num_predict": spec.get("max_tokens", 220) if max_tokens is None else max_tokens,
    }
    payload = {
        "model": spec["model"],
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": build_user_prompt(rows)},
        ],
        "stream": False,
        "options": options,
    }
    if think is not None:
        payload["think"] = think

    data = json.dumps(payload).encode("utf-8")
    endpoint = ollama_endpoint(spec["base_url"])
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        sys.exit(f"model request failed for {spec['model']} at {endpoint}: {exc}")

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        sys.exit(f"model response was not JSON: {exc}")

    message = result.get("message") if isinstance(result, dict) else None
    if not isinstance(message, dict):
        message = {}
    content = message.get("content", "")
    raw_response = {
        "request": payload,
        "native_response": result,
        "choices": [{
            "message": message,
            "finish_reason": result.get("done_reason") or ("stop" if result.get("done") else None),
        }],
        "usage": {
            "prompt_tokens": result.get("prompt_eval_count"),
            "completion_tokens": result.get("eval_count"),
        },
    }
    return content, raw_response


def call_mlx(spec, rows, instruction, *, temperature=None, max_tokens=None):
    from mlx_lm import generate, load

    if "_loaded" not in spec:
        spec["_loaded"] = load(spec["model"])
    model, tokenizer = spec["_loaded"]
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": build_user_prompt(rows)},
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False,
    )
    temp = spec.get("temperature", 0.8) if temperature is None else temperature
    tokens = spec.get("max_tokens", 220) if max_tokens is None else max_tokens
    try:
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=temp)
        text = generate(model, tokenizer, prompt=prompt, max_tokens=tokens, sampler=sampler, verbose=False)
    except (ImportError, TypeError):
        try:
            text = generate(model, tokenizer, prompt=prompt, max_tokens=tokens, temp=temp, verbose=False)
        except TypeError:
            text = generate(model, tokenizer, prompt, max_tokens=tokens)
    return text, {"backend": "mlx", "model": spec["model"], "content": text}


def call_model(spec, rows, instruction, *, temperature=None, max_tokens=None, timeout=120, think=None):
    backend = spec.get("backend", "openai-compatible")
    if backend == "mlx":
        return call_mlx(spec, rows, instruction, temperature=temperature, max_tokens=max_tokens)
    if backend == "openai-compatible":
        return call_chat_completion(
            spec,
            rows,
            instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            think=think,
        )
    sys.exit(f"unsupported backend: {backend}")


def strip_code_fence(text):
    stripped = text.strip()
    match = re.fullmatch(r"```(?:jsonl|json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return match.group(1).strip() if match else stripped


def strip_non_json_preamble(text):
    stripped = strip_code_fence(text)
    think_end = stripped.rfind("</think>")
    if think_end >= 0:
        stripped = stripped[think_end + len("</think>"):].lstrip()
    if stripped.startswith(("{", "[")):
        return stripped
    json_start = stripped.find("{")
    if json_start >= 0:
        stripped = stripped[json_start:]
    return stripped


def parse_json_container(text):
    stripped = strip_non_json_preamble(text)
    if not stripped:
        return None
    if stripped[0] not in "[{":
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("rows", "outputs", "drafts"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return None


def parse_labeled_backtick_rows(text):
    rows = []
    for match in re.finditer(r'(?:^|\n)\s*Row\s+\d+\s*:\s*`(\{[^\n]*?\})`', text):
        try:
            rows.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return rows or None


def parse_output(text, source, allow_partial=False):
    labeled_rows = parse_labeled_backtick_rows(text)
    if labeled_rows is not None:
        return labeled_rows

    container_rows = parse_json_container(text)
    if container_rows is not None:
        return container_rows

    rows = []
    for line_no, line in enumerate(strip_non_json_preamble(text).splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            try:
                repaired = repair_jsonl_line(line)
            except ValueError:
                repaired = None
            if repaired is None:
                if allow_partial:
                    continue
                sys.exit(f"{source}:{line_no}: invalid JSONL from model: {exc}")
            rows.append(repaired)
    if not rows and allow_partial:
        return rows
    return rows


def repair_jsonl_line(line):
    stripped = line.strip()
    if stripped.startswith("{") and not stripped.endswith("}"):
        try:
            return json.loads(stripped + "}")
        except json.JSONDecodeError:
            return None
    polluted = repair_polluted_output_line(stripped)
    if polluted is not None:
        return polluted
    return None


def repair_polluted_output_line(line):
    id_matches = re.findall(r':\s*"(tweet:\d+)"', line)
    draft_match = re.search(r'"draft"\s*:\s*"(.*)"\s*}$', line)
    if not id_matches or not draft_match:
        return None
    try:
        draft = json.loads('"' + draft_match.group(1) + '"')
    except ValueError:
        return None
    return {
        "id": id_matches[-1],
        "draft": draft,
    }


def normalize_id(value):
    return re.sub(r"^(?:<0x[0-9A-Fa-f]{2}>|\s)+", "", str(value)).strip()


def comparable_id(value, expected=None):
    normalized = normalize_id(value)
    expected_normalized = normalize_id(expected) if expected is not None else None
    if expected_normalized and re.fullmatch(r"tweet:\d+", expected_normalized):
        expected_digits = expected_normalized.split(":", 1)[1]
        match = re.search(r":(\d+)$", normalized)
        if match:
            return f"tweet:{match.group(1)}"
        output_digits = "".join(re.findall(r"\d+", normalized))
        if len(output_digits) >= 12 and expected_digits.endswith(output_digits):
            return expected_normalized
    return normalized


def raw_response_path(raw_response_dir, outputs_dir, output_path):
    raw_dir = Path(raw_response_dir) if raw_response_dir else outputs_dir / DEFAULT_RAW_RESPONSE_DIRNAME
    return raw_dir / f"{output_path.stem}.response.json"


def invalid_rows_path(invalid_row_dir, outputs_dir, output_path):
    invalid_dir = Path(invalid_row_dir) if invalid_row_dir else outputs_dir / DEFAULT_INVALID_ROW_DIRNAME
    return invalid_dir / f"{output_path.stem}.invalid.jsonl"


def retry_inputs_path(retry_input_dir, outputs_dir, input_path):
    retry_dir = Path(retry_input_dir) if retry_input_dir else outputs_dir / DEFAULT_RETRY_INPUT_DIRNAME
    return retry_dir / f"{input_path.stem}.retry.jsonl"


def save_raw_response(path, *, request_model, output_path, extracted_content, raw_response):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {
            "model": request_model,
            "output_path": str(output_path),
            "extracted_content": extracted_content,
            "raw_response": raw_response,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n")


def write_invalid_rows(path, records):
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))


def write_retry_inputs(path, records):
    retry_rows = [record["input"] for record in records if record.get("input")]
    if not retry_rows:
        return
    write_jsonl(path, retry_rows)


def invalid_row_record(source, idx, reason, input_row, output_row):
    return {
        "source": source,
        "row": idx,
        "reason": reason,
        "input": input_row,
        "output": output_row,
    }


def reject_or_record(invalid_records, source, idx, reason, input_row, output_row):
    if invalid_records is None:
        sys.exit(f"{source}: row {idx} {reason}")
    invalid_records.append(invalid_row_record(source, idx, reason, input_row, output_row))


def output_matches_expected_id(output_row, input_row):
    if not isinstance(output_row, dict) or "id" not in output_row:
        return False
    return comparable_id(output_row["id"], expected=input_row["id"]) == comparable_id(input_row["id"])


def output_matches_any_input(output_row, input_rows):
    return any(output_matches_expected_id(output_row, input_row) for input_row in input_rows)


def quarantine_extra_output_rows(input_rows, output_rows, source, invalid_records):
    kept = []
    seen_input_indexes = set()
    for idx, output_row in enumerate(output_rows, 1):
        matched_index = None
        for input_index, input_row in enumerate(input_rows):
            if output_matches_expected_id(output_row, input_row):
                matched_index = input_index
                break
        if matched_index is not None:
            if matched_index not in seen_input_indexes:
                seen_input_indexes.add(matched_index)
                kept.append(output_row)
                continue
            reason = "duplicate output row for expected id"
        else:
            reason = "unexpected extra output row"
        invalid_records.append(invalid_row_record(
            source,
            idx,
            reason,
            None,
            output_row,
        ))
    output_rows[:] = kept


def quarantine_missing_input_rows(input_rows, output_rows, source, invalid_records):
    output_by_input_index = {}
    for output_row in output_rows:
        for input_index, input_row in enumerate(input_rows):
            if input_index not in output_by_input_index and output_matches_expected_id(output_row, input_row):
                output_by_input_index[input_index] = output_row
                break

    aligned_rows = []
    for input_index, input_row in enumerate(input_rows):
        output_row = output_by_input_index.get(input_index)
        if output_row is None:
            invalid_records.append(invalid_row_record(
                source,
                input_index + 1,
                "missing output row for expected id",
                input_row,
                None,
            ))
            continue
        aligned_rows.append(output_row)
    output_rows[:] = aligned_rows


def quarantine_unparseable_chunk(input_rows, source, invalid_rows_file, retry_inputs_file, reason):
    invalid_records = [
        invalid_row_record(source, idx, reason, input_row, None)
        for idx, input_row in enumerate(input_rows, 1)
    ]
    write_invalid_rows(invalid_rows_file, invalid_records)
    if retry_inputs_file:
        write_retry_inputs(retry_inputs_file, invalid_records)
    return invalid_records


def validate_output_skip(input_rows, output_rows, source, invalid_rows_file, retry_inputs_file):
    invalid_records = []
    matched_outputs = {}
    unmatched_outputs = []
    invalid_input_indexes = set()

    for output_idx, output_row in enumerate(output_rows, 1):
        matched_input_idx = None
        for input_idx, input_row in enumerate(input_rows):
            if output_matches_expected_id(output_row, input_row):
                matched_input_idx = input_idx
                break

        if matched_input_idx is None:
            unmatched_outputs.append((output_idx, output_row))
            continue
        if matched_input_idx in matched_outputs:
            invalid_records.append(invalid_row_record(
                source,
                output_idx,
                "duplicate output row for expected id",
                None,
                output_row,
            ))
            continue
        matched_outputs[matched_input_idx] = output_row

    for output_idx, output_row in unmatched_outputs:
        fallback_input_idx = output_idx - 1
        if fallback_input_idx < len(input_rows) and fallback_input_idx not in matched_outputs:
            input_row = input_rows[fallback_input_idx]
            invalid_input_indexes.add(fallback_input_idx)
            invalid_records.append(invalid_row_record(
                source,
                output_idx,
                f"id mismatch: expected {input_row['id']}, got {output_row.get('id') if isinstance(output_row, dict) else output_row}",
                input_row,
                output_row,
            ))
            continue
        invalid_records.append(invalid_row_record(
            source,
            output_idx,
            "unexpected extra output row",
            None,
            output_row,
        ))

    valid_rows = []
    for input_idx, input_row in enumerate(input_rows):
        if input_idx in invalid_input_indexes:
            continue
        output_row = matched_outputs.get(input_idx)
        if output_row is None:
            invalid_records.append(invalid_row_record(
                source,
                input_idx + 1,
                "missing output row for expected id",
                input_row,
                None,
            ))
            continue
        if set(output_row) != {"id", "draft"}:
            reject_or_record(
                invalid_records,
                source,
                input_idx + 1,
                "must contain exactly id and draft",
                input_row,
                output_row,
            )
            continue
        draft = str(output_row.get("draft", "")).strip()
        if not draft:
            reject_or_record(invalid_records, source, input_idx + 1, "draft is empty", input_row, output_row)
            continue
        if draft == str(input_row.get("final", "")).strip():
            reject_or_record(
                invalid_records,
                source,
                input_idx + 1,
                f"draft equals final for {input_row['id']}",
                input_row,
                output_row,
            )
            continue
        output_row["id"] = input_row["id"]
        output_row["draft"] = draft
        valid_rows.append(output_row)

    if invalid_records:
        write_invalid_rows(invalid_rows_file, invalid_records)
        if retry_inputs_file:
            write_retry_inputs(retry_inputs_file, invalid_records)
    output_rows[:] = valid_rows
    return invalid_records


def validate_output(input_rows, output_rows, source, invalid_rows_file=None, retry_inputs_file=None):
    invalid_records = [] if invalid_rows_file else None
    if invalid_records is not None:
        return validate_output_skip(input_rows, output_rows, source, invalid_rows_file, retry_inputs_file)

    if len(input_rows) != len(output_rows):
        if invalid_records is None or len(output_rows) < len(input_rows):
            sys.exit(f"{source}: expected {len(input_rows)} rows, got {len(output_rows)}")
        quarantine_extra_output_rows(input_rows, output_rows, source, invalid_records)
        if len(output_rows) < len(input_rows):
            quarantine_missing_input_rows(input_rows, output_rows, source, invalid_records)
        if len(input_rows) != len(output_rows):
            sys.exit(f"{source}: expected {len(input_rows)} rows, got {len(output_rows)} after quarantining extras")

    valid_rows = []
    for idx, (input_row, output_row) in enumerate(zip(input_rows, output_rows), 1):
        if set(output_row) != {"id", "draft"}:
            reject_or_record(
                invalid_records,
                source,
                idx,
                "must contain exactly id and draft",
                input_row,
                output_row,
            )
            continue
        input_id = comparable_id(input_row["id"])
        output_id = comparable_id(output_row["id"], expected=input_row["id"])
        if output_id != input_id:
            reject_or_record(
                invalid_records,
                source,
                idx,
                f"id mismatch: expected {input_row['id']}, got {output_row['id']}",
                input_row,
                output_row,
            )
            continue
        draft = str(output_row.get("draft", "")).strip()
        if not draft:
            reject_or_record(invalid_records, source, idx, "draft is empty", input_row, output_row)
            continue
        if draft == str(input_row.get("final", "")).strip():
            reject_or_record(
                invalid_records,
                source,
                idx,
                f"draft equals final for {input_row['id']}",
                input_row,
                output_row,
            )
            continue
        output_row["id"] = input_row["id"]
        output_row["draft"] = draft
        valid_rows.append(output_row)

    if invalid_records:
        write_invalid_rows(invalid_rows_file, invalid_records)
        if retry_inputs_file:
            write_retry_inputs(retry_inputs_file, invalid_records)
        output_rows[:] = valid_rows
    return invalid_records or []


def run(args):
    config = load_config(args.config)
    spec = resolve_model(
        config,
        args.model,
        provider=args.provider,
        base_url=args.base_url,
        mlx_model=args.mlx_model,
    )
    instruction = TEMPLATE.read_text()

    gen_dir = generation_dir(args)
    model_dir = gen_dir / args.model
    inputs_dir = model_dir / "inputs"
    outputs_dir = model_dir / "outputs"
    if not inputs_dir.exists():
        sys.exit(f"missing inputs directory: {inputs_dir}")

    indexes = selected_indexes(inputs_dir, args.start, args.end)
    print(f"model: {args.model} ({spec.get('provider', spec.get('base_url', spec.get('backend')))})")
    print(f"chunks: {indexes[0]:03d}..{indexes[-1]:03d} ({len(indexes)} files)")

    if args.dry_run:
        rows = sum(len(read_jsonl(inputs_dir / f"{idx:03d}.input.jsonl")) for idx in indexes)
        print(f"dry run: would generate {rows} drafts into {outputs_dir}")
        return

    outputs_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    drafts = 0
    for idx in indexes:
        input_path = inputs_dir / f"{idx:03d}.input.jsonl"
        output_path = outputs_dir / f"{idx:03d}.output.jsonl"
        if output_path.exists() and not args.overwrite:
            sys.exit(f"{output_path} already exists; pass --overwrite to replace it")

        input_rows = read_jsonl(input_path)
        text, raw_response = call_model(
            spec,
            input_rows,
            instruction,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            think=args.think,
        )
        raw_path = raw_response_path(args.raw_response_dir, outputs_dir, output_path)
        if args.raw_response_dir:
            save_raw_response(
                raw_path,
                request_model=spec["model"],
                output_path=output_path,
                extracted_content=text,
                raw_response=raw_response,
            )
        if args.debug_response:
            print(f"debug: extracted {len(text or '')} characters from response")
        if not strip_code_fence(text or ""):
            if not args.raw_response_dir:
                save_raw_response(
                    raw_path,
                    request_model=spec["model"],
                    output_path=output_path,
                    extracted_content=text,
                    raw_response=raw_response,
                )
            reasoning_chars, finish_reason = reasoning_details(raw_response)
            if reasoning_chars:
                hint = (
                    f"model returned empty content but {reasoning_chars} reasoning characters"
                    f" (finish_reason={finish_reason!r}); raw response saved to {raw_path}. "
                    "For thinking models, retry with --think off and/or a larger --max-tokens."
                )
                sys.exit(f"{output_path}: {hint}")
            sys.exit(f"{output_path}: model returned empty content; raw response saved to {raw_path}")
        try:
            invalid_file = None
            retry_file = None
            if args.invalid_row_action == "skip":
                invalid_file = invalid_rows_path(args.invalid_row_dir, outputs_dir, output_path)
                retry_file = retry_inputs_path(args.retry_input_dir, outputs_dir, input_path)
            if args.invalid_row_action == "skip" and not strip_non_json_preamble(text or "").startswith(("{", "[")):
                output_rows = []
                invalid_records = quarantine_unparseable_chunk(
                    input_rows,
                    str(output_path),
                    invalid_file,
                    retry_file,
                    "model response contained no parseable JSON output",
                )
            else:
                output_rows = parse_output(
                    text,
                    str(output_path),
                    allow_partial=args.invalid_row_action == "skip",
                )
                invalid_records = validate_output(input_rows, output_rows, str(output_path), invalid_file, retry_file)
        except SystemExit:
            if not args.raw_response_dir:
                save_raw_response(
                    raw_path,
                    request_model=spec["model"],
                    output_path=output_path,
                    extracted_content=text,
                    raw_response=raw_response,
                )
            raise
        write_jsonl(output_path, output_rows)
        written += 1
        drafts += len(output_rows)
        if invalid_records:
            print(f"wrote {output_path} ({len(output_rows)} rows, {len(invalid_records)} invalid rows quarantined)")
        else:
            print(f"wrote {output_path} ({len(output_rows)} rows)")

    print(f"done: wrote {written} files, {drafts} drafts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="draft model folder/config key")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--provider", choices=["lmstudio", "ollama"], default=None)
    parser.add_argument("--base-url", default=None, help="override OpenAI-compatible base URL")
    parser.add_argument("--mlx-model", default=None, help="run this MLX model id/path instead of HTTP")
    parser.add_argument("--generation-date", default=date.today().isoformat())
    parser.add_argument("--generation-dir", type=Path, default=None)
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--think",
        choices=["auto", "on", "off"],
        default=None,
        help="set provider thinking mode when supported, e.g. Ollama thinking models; use off for JSONL generation",
    )
    parser.add_argument(
        "--raw-response-dir",
        type=Path,
        default=None,
        help="write raw model responses for debugging; defaults to outputs/_raw_responses on empty responses",
    )
    parser.add_argument("--debug-response", action="store_true", help="print extracted response lengths")
    parser.add_argument(
        "--invalid-row-action",
        choices=["fail", "skip"],
        default="fail",
        help="fail on invalid rows, or skip them and write review records",
    )
    parser.add_argument(
        "--invalid-row-dir",
        type=Path,
        default=None,
        help="directory for skipped invalid-row review records; defaults to outputs/_invalid_rows",
    )
    parser.add_argument(
        "--retry-input-dir",
        type=Path,
        default=None,
        help="directory for retry input rows from skipped invalid rows; defaults to outputs/_retry_inputs",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
