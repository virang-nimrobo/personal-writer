.PHONY: install venv import-twitter smoke train infer eval promote harvest ui draft-models draft-generation clean

# use the project venv if present, else system python3
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
ADAPTER ?= out/editor-candidate
EVAL_ADAPTER ?= $(ADAPTER)
DRAFT_MODEL_CONFIG := data_prep/draft_models.json
GENERATION_DATE ?= $(shell date +%F)
MODEL ?=
START ?= 0
END ?= 10

venv:
	python3 -m venv .venv && .venv/bin/python -m pip install -U pip

install: venv
	.venv/bin/python -m pip install -r requirements.txt

# --- training ---
# Data prep now lives in data_prep/ (fetch_x_core -> build_generation ->
# build_triplets -> landing_zone/triplets.jsonl); `train` consumes that file.

import-twitter:                # Twitter/X archive -> data_prep/core/no_draft.jsonl
	$(PY) data_prep/import_twitter_archive.py

smoke:                        # tiny end-to-end run: validates the chain + that BASE_MODEL trains/loads
	$(PY) scripts/05_build_dataset.py
	bash scripts/06_train_lora.sh --smoke
	$(PY) scripts/08_infer.py --smoke

train:
	$(PY) scripts/validate_landing_zone.py
	$(PY) scripts/05_build_dataset.py
	ADAPTER=$(ADAPTER) bash scripts/06_train_lora.sh

infer:
	$(PY) scripts/08_infer.py

eval:
	$(PY) scripts/07_eval.py --adapter $(EVAL_ADAPTER)

promote:
	$(PY) training/promote.py --candidate $(ADAPTER) --champion out/editor-latest

harvest:                      # Phase 2: pull edit-pairs from live Xgrowth runs
	$(PY) scripts/09_harvest.py

ui:                           # Phase 3: pairwise A/B + inline-edit labeling app
	$(PY) ui/app.py

draft-models:                 # list local draft-generation aliases from data_prep/draft_models.json
	$(PY) -c 'import json; print("\n".join(json.load(open("$(DRAFT_MODEL_CONFIG)"))["models"].keys()))'

draft-generation:             # MODEL=<alias> [GENERATION_DATE=YYYY-MM-DD] [START=0] [END=10]
	@test -n "$(MODEL)" || (echo "MODEL is required. Run 'make draft-models' to list aliases."; exit 2)
	$(PY) -c 'import json,sys; models=json.load(open("$(DRAFT_MODEL_CONFIG)"))["models"]; sys.exit(0 if "$(MODEL)" in models else "unknown MODEL=$(MODEL); run make draft-models")'
	$(PY) data_prep/build_generation.py --date $(GENERATION_DATE) --models $(MODEL)
	$(PY) data_prep/run_draft_generation.py --model $(MODEL) --generation-date $(GENERATION_DATE) --start $(START) --end $(END)

clean:
	rm -rf data/processed/* data/synth/* out/smoke
