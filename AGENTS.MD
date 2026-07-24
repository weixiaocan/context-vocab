# AGENTS

## Project Context

This is a personal vocabulary-retention tool for reading English technical material. The product goal is not to teach English broadly; it is to reduce the chance that a word seen during real reading feels unfamiliar the next time it appears.

The main user is the project owner. Optimize for low-friction daily use over feature completeness.

## Source Of Truth

- Current code and observed usage behavior are the primary source of truth.
- `docs/PRD.md` and `docs/ARCHITECTURE.md` are initial planning documents from the start of development. They are useful historical context, but later development does not need to follow them blindly.
- If the early docs conflict with the current code, actual user feedback, or a concrete bug found during use, prefer the current evidence and update the implementation accordingly.

## Important Product Constraint

Multiple-choice distractors are a recurring quality risk.

Do not generate answer options that are just a pile of acceptable near-synonyms. A card is bad if several options can reasonably be correct in the sentence context, even if each option is linguistically related.

Examples of bad option sets:

- `严谨的 / 严密的 / 精确的` for `rigorous` in a sentence about designing better evals.
- `揭秘 / 阐释 / 澄清` for `demystifying` when several Chinese renderings are acceptable.

The intended constraint is:

- The correct answer should express the target word's meaning in that sentence.
- Distractors should be same broad part of speech and related enough to be plausible at a glance.
- Distractors must still have a clear semantic error when placed back into the sentence.
- If several Chinese choices are all acceptable translations, the card should be regenerated or manually corrected.

This is not about banning specific words like `揭秘`; it is about making the question discriminative and fair.

## Development Notes

- Keep the system small and runnable end to end.
- Do not add motivational mechanics, streaks, scoring systems, or broad language-learning features unless explicitly requested.
- Prefer deterministic code and tests for deterministic behavior.
- LLM output is cached content, but it is not automatically trustworthy. Add validation or manual correction paths when usage exposes repeatable quality failures.

## Git Push Policy

- Do not push after every small edit.
- Prefer pushing at useful checkpoints:
  - after completing a coherent feature, bug fix, or behavior change;
  - after local tests or manual verification pass;
  - before ending a work session if code was changed and the app is in a runnable state;
  - during long sessions, roughly every 30-60 minutes when there is a stable checkpoint.
- Avoid pushing broken or obviously unfinished intermediate states unless explicitly asked.
- Keep commits small enough to understand, but not so small that every file tweak becomes a remote push.

## Deployment Status

- Server: Alibaba Cloud ECS, Hong Kong region, Ubuntu 22.04, 2 vCPU/2 GiB.
- Domain: `vocab.weixiaocan.com`; HTTPS is provided by Caddy with automatic certificates.
- Runtime: Docker Compose; `vocab-server` is private on `127.0.0.1:8001`, Caddy exposes ports 80/443.
- Data: SQLite at `server/data/vocab.db`, persisted outside the container. Back up before updates.
- Security: keep `server/.env` and `ACCESS_TOKEN` out of Git; never expose secrets in logs or chat. Do not open port 8001 publicly.
- Update flow: local test → commit/push → server `git pull --ff-only` → `docker compose up -d --build` → health-check `/health`.
- Current state: deployed and verified; local vocabulary data has been migrated to the server.
