---
paths:
  - "data/**"
  - "scripts/**"
  - "evals/**"
  - "docs/DATASETS.md"
---

# Data governance rules

- A dataset enters the pipeline only after it is in `data/dataset_registry.yaml` with source, access date,
  version, checksum, license, commercial-use status and purpose.
- Non-commercial datasets (for example CC BY-NC) are for research and evaluation only unless rights are obtained.
- Keep raw downloads unchanged under `data/raw/`; derived files go to `data/interim/` or `data/processed/` through
  versioned scripts.
- Aggregate statistics are benchmarks, never incident facts about a person or employer.
- Synthetic data must be labelled synthetic wherever it is shown.
- Do not commit customer data, personal data or licensed standards text.
