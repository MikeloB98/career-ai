# Career AI

Career AI is a local-first, provider-neutral workflow for turning verified career
evidence and explicit goals into job evaluations and tailored application content.

It is not an auto-apply bot. Models perform bounded semantic work; local code owns file
custody, hashes, schemas and state. Users approve every application and perform every
external action themselves.

## Install

Python 3.11 or newer is required.

```bash
pipx install git+https://github.com/YOUR-USER/career-ai.git
```

For local development:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/career-ai --version
```

## Create a private workspace

```bash
career-ai init ~/career-workspace
cd ~/career-workspace
career-ai doctor
```

The generated workspace keeps real profile, vacancy and application files under
`private/`, which is ignored by Git.

Prepare two Markdown files:

- a factual professional profile containing only verified information;
- an explicit career strategy containing goals, preferences, constraints and unknowns.

Then onboard them:

```bash
career-ai onboard \
  --name "Your Name" \
  --profile /path/to/profile.md \
  --strategy /path/to/strategy.md
```

## Register and evaluate a vacancy

```bash
career-ai jobs add vacancy.md \
  --company "Example Company" \
  --role "Materials Engineer" \
  --source-url "https://example.com/jobs/123"

career-ai jobs list
career-ai evaluate prepare JOB_ID
```

The default `manual-agent` provider creates a hash-bound prompt. Run it in OpenCode,
Codex or another agent, save the returned JSON and import it:

```bash
career-ai ai import private/requests/REQUEST.json output.json
```

For a positive or considered decision, explicitly authorize drafting:

```bash
career-ai application prepare JOB_ID \
  --decision private/outputs/EVALUATION.json \
  --authorize
```

Nothing is submitted automatically.

## OpenCode

Every workspace includes project-local Career PM, Planner, Scout, Evaluator and Writer
agents plus reusable skills. The project does not pin a model.

```bash
opencode ~/career-workspace
```

Inside OpenCode:

```text
/career-status
/career-evaluate JOB_ID
/career-write JOB_ID --decision private/outputs/EVALUATION.json --authorize
```

OpenCode also supports non-interactive execution:

```bash
opencode run --dir ~/career-workspace --agent career-pm \
  "Inspect the workspace and explain the next checkpoint"
```

## Direct model APIs

Workspace configuration supports:

- OpenAI Responses;
- OpenAI-compatible Chat Completions;
- manual execution through any agent runtime.

HTTP providers are disabled by default and blocked from receiving personal data until
the workspace owner explicitly sets `allow_personal_data: true` after reviewing that
provider's privacy terms. Credentials are read only from environment variables.

## Current scope

Version 0.1 provides a safe manual vertical slice: onboarding, vacancy registration,
bounded evaluation, text-only application content and OpenCode integration. Automated
job-source acquisition, recurring schedules, market intelligence, networking and a web
interface remain future work.

See [SECURITY.md](SECURITY.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
