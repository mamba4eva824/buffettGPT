# Promotion Workflow: Feature → Dev → Staging

Buffett uses a **linear promotion model**. Code flows in one direction across three branch tiers; environment-specific configuration stays put.

```
feature/* (or fix/*, chore/*)  ──PR──▶  dev  ──promote PR──▶  staging
```

`main` exists for release tagging only — both deploy workflows are driven by `dev` and `staging` branches respectively.

---

## Daily flow

### 1. Build a feature

```bash
git checkout dev && git pull
git checkout -b feature/my-thing
# ...code...
git push -u origin feature/my-thing
gh pr create --base dev --title "feat: my thing"
```

`deploy-dev.yml` runs when the PR merges. The dev environment serves as the "fast iteration" sandbox — pipelines and EventBridge schedules are off (manual invokes refresh data).

### 2. Promote dev → staging when ready

When `dev` has a coherent set of changes you want on staging:

**One-click via GitHub UI** (recommended):
1. Open https://github.com/{owner}/{repo}/actions/workflows/promote-dev-to-staging.yml
2. Click **"Run workflow"** → branch `staging` → **Run**
3. Wait ~30 seconds for the workflow to open a PR on a `promote/dev-to-staging-{run-id}` branch
4. Review the PR (env-specific files have already been filtered out — see below)
5. Merge → `deploy-staging.yml` runs

**One-click via CLI**:
```bash
gh workflow run promote-dev-to-staging.yml --ref staging
```

The PR's branch will be named `promote/dev-to-staging-{github-run-id}` (collision-proof for same-day re-runs). Labels `promotion` + `automated` are applied automatically.

### 3. Production (when ready)

`deploy-prod.yml` requires a manual GitHub Environment approval. Out of scope for this doc.

---

## What the promotion workflow does

`.github/workflows/promote-dev-to-staging.yml` is a `workflow_dispatch`-only helper. Each run:

1. **Stale-PR check** — if there's already an open PR labeled `promotion`, skip and tell the user to close/merge it first. Prevents duplicates.
2. **Branch off `staging`** — `promote/dev-to-staging-{run_id}`.
3. **Merge `origin/dev` with `--no-commit --no-ff`** — captures all the dev changes but doesn't finalize yet.
4. **Revert excluded paths** to staging's pre-merge state. The exclusion list is the heart of the workflow — see below.
5. **Audit step** — hard-fails if any excluded path leaked into the staged diff. This catches new env-specific files added later that the exclusion list hasn't been updated for.
6. **No-op check** — if the diff is empty after exclusions (everything shared is already on staging), aborts the merge cleanly without opening a PR.
7. **Commit + push** with retry on race (rebase if someone pushed to staging mid-run).
8. **Open PR** with body listing the commits being promoted + a reviewer checklist + a kill switch reminder.

### Conflict handling

If `git merge` hits a conflict on a non-excluded path, the workflow:
- Stages everything (conflict markers and all)
- Commits as `CONFLICT, requires human resolution`
- Pushes the branch
- Opens a **DRAFT** PR with instructions for the reviewer

This usually means a hotfix landed directly on staging without going through dev. Rare but legitimate.

---

## Excluded paths (never auto-promote)

These paths are reverted to staging's pre-merge state by every promotion run. They're env-specific by design and would corrupt staging if blindly synced:

| Path | Why excluded |
|---|---|
| `chat-api/terraform/environments/dev/` | dev tfvars, dev backend.hcl, dev's `main.tf` (different module flags) |
| `chat-api/terraform/environments/staging/` | staging is the target — preserving its `main.tf` is the whole point |
| `.github/workflows/deploy-dev.yml` | dev-only Docker matrix, dev secrets, branch trigger |
| `.github/workflows/deploy-staging.yml` | staging-only frontend deploy job, basic_auth_credentials |
| `.github/workflows/promote-dev-to-staging.yml` | Don't let a stale dev branch overwrite the workflow itself |
| `frontend/.env.development` | Hardcoded dev API Gateway / Function URLs |
| `frontend/.env.staging` | Hardcoded staging URLs (CloudFront origin etc.) |
| `frontend/.env.production` | Hardcoded prod URLs |
| `docs/market-intelligence/CHANGELOG.md` | Drifts continuously; hand-update on phase PRs to avoid merge conflicts every run |

**Adding a new env-specific path**: edit `EXCLUDED` in `.github/workflows/promote-dev-to-staging.yml` AND the audit-step regex (the regex is the safety net that catches unmaintained drift).

---

## Reverse direction (staging → dev)

Sometimes staging accumulates changes dev doesn't have (e.g., the staging-only password gate, free-tier Market Intelligence access). When dev branch needs to catch up — typically before pushing a change that depends on the latest module shape — open a manual `sync/staging-to-dev` PR:

```bash
git fetch origin staging
git checkout -b sync/staging-to-dev origin/dev
git merge origin/staging
# resolve any conflicts (the exclusion list above also applies in reverse)
gh pr create --base dev --title "sync(dev): merge staging back"
```

This is a **rare** operation — it's only needed when env-specific files on staging that "leak" into shared modules diverge from what dev expects. PR #47 was the most recent example (after Phase 1.5 + 2 had piled up on staging).

---

## Kill switch

If the promotion workflow misbehaves:

```bash
gh workflow disable promote-dev-to-staging.yml
```

The workflow stays in the repo but won't accept `workflow_dispatch` triggers until re-enabled with `gh workflow enable`.

To remove it entirely: delete `.github/workflows/promote-dev-to-staging.yml` in a regular PR.

---

## FAQ

**Q: Why not run on a cron schedule?**
A: Phase rollouts (e.g., the dev→staging EventBridge schedule split in Phase 3a/3b) need human gating. A cron would have promoted dev's "disable schedules" change to staging while staging was deliberately enabling its own schedules. Manual `workflow_dispatch` keeps you in control of when promotions happen.

**Q: Why no auto-merge?**
A: GitHub's recursion guard means PRs opened by `GITHUB_TOKEN` don't trigger `deploy-staging.yml`'s checks pre-merge. Auto-merging would deploy without any pre-merge validation. Human review is the gate.

**Q: What if I want to promote ONE specific commit, not everything on dev?**
A: Open a feature branch off staging, cherry-pick the commit, and PR it manually. The promotion workflow is for "all current shared changes on dev are ready" — for selective promotion, use cherry-pick.

**Q: What if the workflow audit step fails?**
A: That means a new env-specific file was added without updating the exclusion list. Edit `promote-dev-to-staging.yml` to include the new path in BOTH the `EXCLUDED` array AND the audit-step regex, then merge that fix and re-run promotion.

**Q: Can I promote when dev's last deploy was red?**
A: The workflow doesn't enforce this — it would skip promotion automatically only if you wired in a `gh run list ... --jq '.[0].conclusion'` gate. For now, it's a soft convention: don't run promotion if dev is broken.
