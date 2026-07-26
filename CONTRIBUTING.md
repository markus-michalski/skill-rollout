# Contributing to skill-rollout

Thank you for your interest. This document explains how to contribute and what to expect.

## Governance Model

skill-rollout follows a **Benevolent Dictator For Life (BDFL)** model. [Markus Michalski](https://github.com/markus-michalski) is the sole maintainer with final say on all changes, direction, and releases. Contributions are welcome within that structure.

## License & CLA

**Important — read this before opening a PR:**

1. This project is licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE.md)**. It is source-available but **not** OSI Open Source. Commercial use is prohibited.
2. All contributors must sign the **[Contributor License Agreement (CLA)](CLA.md)** before their PR can be merged. The [cla-assistant.io](https://cla-assistant.io/) bot will comment on your PR with a one-click signing link.

Why a CLA? The CLA grants the maintainer the rights needed to keep the project viable (relicensing flexibility, legal protection). Without it, your contribution cannot be accepted.

## Branch Model

Single-branch model:

- **`main`** — the only long-lived branch. Always in a releasable state.
- **Feature branches** — short-lived, branched from `main`, merged via PR.

Branch naming:

- `feat/description` — new features
- `fix/description` — bug fixes
- `docs/description` — documentation
- `chore/description` — maintenance
- `refactor/description` — refactoring

## Development Workflow

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR-USERNAME/skill-rollout.git
cd skill-rollout
git remote add upstream https://github.com/markus-michalski/skill-rollout.git
```

### 2. Create a Feature Branch

```bash
git checkout main
git pull upstream main
git checkout -b feat/your-feature-name
```

### 3. Set Up Local Development

```bash
# Create venv for the MCP server
python3 -m venv ~/.skill-rollout/venv
~/.skill-rollout/venv/bin/pip install -r requirements.txt

# Install dev dependencies
~/.skill-rollout/venv/bin/pip install -r requirements-dev.txt
```

### 4. Make Your Changes

Follow existing code patterns. For each change type:

- **New skill**: Create `skills/your-skill/SKILL.md` with frontmatter (`name`, `description`, `model`, `user-invocable: true`). Add routing entry to `CLAUDE.md`. Add entry to `skills/help/SKILL.md`.
- **New MCP tool**: Add to `servers/skill-rollout-server/`. Export via the server's tool registry.
- **Workflow script changes** (`workflows/skill-rollout.js`): Test against a real plugin rollout before submitting. Describe the behavioral change in the PR.
- **Eval schema** (`reference/eval-schema.md`): Changes affect how all target plugins are classified — include justification and examples in the PR.

### 5. Test Locally

```bash
# Run all smoke tests
~/.skill-rollout/venv/bin/python -m pytest tests/smoke -q

# Lint
ruff check .

# Format check
ruff format --check .
```

### 6. Commit with Conventional Commits

Format: `<type>(<scope>): <subject>`

| Type | Version Bump |
|------|--------------|
| `feat:` | MINOR |
| `fix:` | PATCH |
| `feat!:` or `BREAKING CHANGE:` | MAJOR |
| `docs:`, `chore:`, `refactor:`, `test:` | None |

Examples:

```
feat(run): add --resume flag to continue from last completed skill
fix(tier): classify read-only MCP surfaces as READ-ONLY, not BLOCKED
docs(contributing): clarify CLA process
chore(deps): bump ruff to 0.9.0
```

When working with Claude Code, include the co-author line:

```
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### 7. Update the Changelog

Add an entry under `[Unreleased]` in `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- feature description (#issue-number)

### Fixed
- bug description (#issue-number)
```

### 8. Push and Open a PR

```bash
git push -u origin feat/your-feature-name
```

Open a PR via the GitHub UI. The PR template will guide you through the checklist. The CLA bot will comment with a signing link on first contribution.

## PR Review Process

1. **Automated checks** must pass (pytest smoke tests on Ubuntu + Windows, ruff lint + format check, JSON validation of `.claude-plugin/plugin.json` + `.mcp.json`, CLA signed)
2. **Maintainer review** — @markus-michalski reviews every PR personally. Expect feedback cycles.
3. **Squash merge** — all PRs are squash-merged into `main` with a Conventional Commit message
4. **Release** — the maintainer batches features into releases and cuts version tags

## Release Process (maintainer only)

Releases are handled by the `release` command in the mm-dev-toolkit. It bumps the version in `.claude-plugin/plugin.json`, moves `[Unreleased]` entries in `CHANGELOG.md` to the new version heading, commits, tags, and pushes — all in one step. Do not do these steps manually; the release script owns the version and CHANGELOG header.

After the script completes, create a GitHub Release from the new tag.

## Code Style

- **Python**: PEP 8, type hints, English comments. Ruff is the formatter and linter.
- **JavaScript** (workflow scripts): ES modules, async/await, English comments.
- **Markdown**: English for reference docs and skill docs.
- **YAML frontmatter**: Required in all `SKILL.md` files (`name`, `description`, `model`, `user-invocable`).
- **`encoding="utf-8"`**: Required on every `Path.open()` / `write_text()` / `read_text()` call — no exceptions.

## What Does NOT Belong in a PR

- Claude API keys, GitHub tokens, or any secrets (see [SECURITY.md](.github/SECURITY.md))
- Commented-out code blocks without justification
- Unrelated refactoring bundled with a feature change
- Documentation for features that haven't shipped yet
- Changes to `LICENSE.md`, `CLA.md`, or `.github/CODEOWNERS` (maintainer-only)
- Manual version bumps in `.claude-plugin/plugin.json` or new CHANGELOG headers — the release script owns those

## Questions

- **Usage questions** → Read the [README](README.md)
- **Feature ideas** → Open a Feature Request issue
- **Bug reports** → Open a Bug Report issue
- **Security issues** → [Private Vulnerability Reporting](https://github.com/markus-michalski/skill-rollout/security/advisories/new)

## Code of Conduct

Be civil. Disagreements about implementation are welcome and encouraged; personal attacks, harassment, or bad-faith behavior are not. The maintainer reserves the right to close issues or block users that cross that line, without explanation.
