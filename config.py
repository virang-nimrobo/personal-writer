"""Central config: paths, data sources, model choices.

Single source of truth for every script. Import as `from config import C`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- data dirs ---
DATA = ROOT / "data"
RAW = DATA / "raw"            # tweets.js dropped here when the X archive arrives
PROCESSED = DATA / "processed"  # unified {context, final} records (jsonl)
CURATED = DATA / "curated"      # trusted minimal training targets
SYNTH = DATA / "synth"        # {context, draft, final} triples (jsonl)
GENERATED = DATA / "generated"  # synthetic tweet generations
PREFS = DATA / "prefs"        # pairwise A/B + inline-edit labels from the UI
FEEDBACK = DATA / "feedback"  # harvested edit-pairs from live Xgrowth runs
USAGE = DATA / "usage"        # append-only raw model usage traces
OUT = ROOT / "out"           # versioned LoRA adapters + scorecards
PROMPTS = ROOT / "prompts"
CONFIGS = ROOT / "configs"
DATA_PREP = ROOT / "data_prep"
LANDING_ZONE = ROOT / "landing_zone"
LANDING_FILE = LANDING_ZONE / "triplets.jsonl"  # unified training input (rebuilt by data_prep/build_triplets.py)
LANDING_TRIPLETS = LANDING_ZONE / "triplets"    # legacy shard dir (unused)
LANDING_MANIFEST = LANDING_ZONE / "manifest.json"  # legacy manifest (unused)
TRAINING = ROOT / "training"
USE = ROOT / "use"
TWEET_PROMPT = PROMPTS / "tweet_prompt.md"
TWEET_PROMPT_GEN1 = PROMPTS / "tweet_prompt_gen1.md"
TWEET_PROMPT_GEN2 = PROMPTS / "tweet_prompt_gen2.md"

# unified intermediate record files
RECORDS_RUNS = PROCESSED / "records_runs.jsonl"
RECORDS_ARCHIVE = PROCESSED / "records_archive.jsonl"
RECORDS_ALL = PROCESSED / "records_all.jsonl"
TARGETS = CURATED / "targets.jsonl"
GENERATIONJSON1 = CURATED / "generationjson1.jsonl"
GENERATIONJSON2 = CURATED / "generationjson2.jsonl"
GENERATED_CHUNKS = GENERATED / "chunks"
GENERATION1_OUTPUTS = GENERATED / "generation1_outputs.jsonl"
GENERATION2_OUTPUTS = GENERATED / "generation2_outputs.jsonl"
GEMINI_GENERATION1_OUTPUTS = ROOT / "gemini" / "gemini_generation1_outputs.jsonl"
GEMINI_GENERATION2_OUTPUTS = ROOT / "gemini" / "gemini_generation2_outputs.jsonl"
TRIPLES = SYNTH / "triples.jsonl"
DATASET_TRAIN = SYNTH / "train.jsonl"
DATASET_VALID = SYNTH / "valid.jsonl"
DATASET_TEST = SYNTH / "test.jsonl"

# --- Xgrowth source loops (where runs/<id>/posts.md|replies.md live) ---
# Add the gen-1 X loop dir here once located; the parser globs runs/* under each.
LOOP_DIRS = [
    Path("/Users/virangjhaveri/nr-loops/Xgrowth"),
]
# Xgrowth taste spec we reuse (do not reinvent the voice rules).
XGROWTH = Path("/Users/virangjhaveri/nr-loops/Xgrowth")
VOICE_MD = XGROWTH / "voice.md"
RUN_MD = XGROWTH / "run.md"

# --- account ---
X_HANDLE = "VirangJhaveri"

# --- models ---
# Primary: capacity for free restructure + invent angle. Lighter A/B: gemma-2-2b-it.
BASE_MODEL = "mlx-community/Qwen3.5-2B-MLX-4bit"
BASE_MODEL_ALT = "mlx-community/gemma-2-2b-it-4bit"

# Adapter that inference (studio/API/CLI) loads by default. Single source of
# truth; writer_model/settings.py reads this so the configs can't drift.
DEFAULT_ADAPTER = OUT / "editor-candidate"

# Big-model used for reverse-synthesis of drafts and as LLM judge.
PLANNER_MODEL = "claude-opus-4-8"
JUDGE_MODEL = "claude-opus-4-8"

# --- generation defaults ---
N_CANDIDATES = 5      # editor samples N (reranker bolts on later)
MAX_TWEET_CHARS = 280

# --- continuous-learning trigger (Phase 4) ---
RETRAIN_MIN_NEW_PAIRS = 50
RETRAIN_MAX_AGE_DAYS = 7

for _d in (
    RAW, PROCESSED, CURATED, SYNTH, GENERATED, PREFS, FEEDBACK, USAGE, OUT,
    DATA_PREP, LANDING_TRIPLETS, TRAINING, USE,
):
    _d.mkdir(parents=True, exist_ok=True)


class C:
    """Namespace handle so scripts can do `from config import C`."""
    ROOT = ROOT
    RAW = RAW; PROCESSED = PROCESSED; CURATED = CURATED; SYNTH = SYNTH
    GENERATED = GENERATED; PREFS = PREFS
    FEEDBACK = FEEDBACK; USAGE = USAGE; OUT = OUT; PROMPTS = PROMPTS; CONFIGS = CONFIGS
    DATA_PREP = DATA_PREP; LANDING_ZONE = LANDING_ZONE; LANDING_FILE = LANDING_FILE
    LANDING_TRIPLETS = LANDING_TRIPLETS; LANDING_MANIFEST = LANDING_MANIFEST
    TRAINING = TRAINING; USE = USE
    TWEET_PROMPT = TWEET_PROMPT
    TWEET_PROMPT_GEN1 = TWEET_PROMPT_GEN1; TWEET_PROMPT_GEN2 = TWEET_PROMPT_GEN2
    RECORDS_RUNS = RECORDS_RUNS; RECORDS_ARCHIVE = RECORDS_ARCHIVE
    RECORDS_ALL = RECORDS_ALL; TARGETS = TARGETS
    GENERATIONJSON1 = GENERATIONJSON1; GENERATIONJSON2 = GENERATIONJSON2
    GENERATED_CHUNKS = GENERATED_CHUNKS
    GENERATION1_OUTPUTS = GENERATION1_OUTPUTS; GENERATION2_OUTPUTS = GENERATION2_OUTPUTS
    GEMINI_GENERATION1_OUTPUTS = GEMINI_GENERATION1_OUTPUTS
    GEMINI_GENERATION2_OUTPUTS = GEMINI_GENERATION2_OUTPUTS
    TRIPLES = TRIPLES
    DATASET_TRAIN = DATASET_TRAIN; DATASET_VALID = DATASET_VALID; DATASET_TEST = DATASET_TEST
    LOOP_DIRS = LOOP_DIRS; XGROWTH = XGROWTH; VOICE_MD = VOICE_MD; RUN_MD = RUN_MD
    X_HANDLE = X_HANDLE
    BASE_MODEL = BASE_MODEL; BASE_MODEL_ALT = BASE_MODEL_ALT
    DEFAULT_ADAPTER = DEFAULT_ADAPTER
    PLANNER_MODEL = PLANNER_MODEL; JUDGE_MODEL = JUDGE_MODEL
    N_CANDIDATES = N_CANDIDATES; MAX_TWEET_CHARS = MAX_TWEET_CHARS
    RETRAIN_MIN_NEW_PAIRS = RETRAIN_MIN_NEW_PAIRS; RETRAIN_MAX_AGE_DAYS = RETRAIN_MAX_AGE_DAYS
