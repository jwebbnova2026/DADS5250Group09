<!-- [AI-authored: Claude] Team to review and complete; the owner of this file is still to be assigned (spec 10.4). -->
# Authorship and AI use

Northeastern's Academic Integrity and Use of AI policy asks us to mark AI-generated work and explain how AI was used. This file does both.

## How AI was used

* **Claude (Anthropic, via Claude Code)** wrote the architecture spec (`docs/architecture.md`) from the project page and team decisions. It revised the spec over four rounds of review by **Codex (OpenAI)**.
* In a single "zero-shot" build on branch `Zero_Shot_Attempt_1`, Claude then wrote all of the following:
  * the `boston311` package, the scripts, and the tests;
  * the dev and test message sets;
  * the notebook, the README sections, and the report draft.
* **The team made every decision recorded in `docs/decisions.md`.** These include the planning year, package structure, provider and model, two-tier routing, the INFO-referral rule, and core-only scope. Claude stopped and asked whenever the data disagreed with the spec.
* **gpt-6.1-sol (OpenAI) is part of the product.** It drafted descriptions and aliases for the 163 official request types (prompt `aliases-v2`). At run time it classifies resident messages (prompt `classify-v2`). Every recorded answer is in `data/demo/recordings.jsonl`.
* **Claude acted as provisional reviewer** for the catalog mappings and aliases, pending team review. Its edits are listed in `docs/decisions.md`.

## Who wrote what

| Item | Author | Status |
|---|---|---|
| Project selection | Nicholas | Done |
| 2025 planning year, package-plus-notebook design, reference notebooks | John | Done |
| Fixed challenge assumptions, deliverables | Teaching team (project page) | GIVEN |
| Architecture spec v5.1 and its later changes | Claude, reviewed by Codex; changes decided by John | See `docs/decisions.md` |
| `src/boston311/` package, `scripts/`, `tests/` | Claude | Reviewed by Astra (`docs/code_review_2026-10-23.md`); findings repaired by Claude; second review and team review pending |
| Code review of `d1d1c7d` | Astra (Codex) | Done 2026-10-23 |
| Catalog mappings (`data/catalog/`) | Computed by code from city data; provisionally approved by Claude | Pending team review |
| Type descriptions and aliases | Drafted by gpt-6.1-sol; reviewed and edited by Claude | Pending team review |
| Dev and test message sets (`data/eval/`) | Claude | Pending team review |
| `demo.ipynb` | Claude | Pending team review |
| `docs/notebook_guide.md` (plain-language walkthrough) | Claude, at John's request | Pending team review |
| `docs/report.md` | Draft by Claude | Andrew and Nicholas to finalize |
| 3-minute video | Andrew and Nicholas | To do |
| README setup, architecture, and team table | Claude | Pending team review |
