"""Command-line application for the portable Career AI workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from career_ai import __version__
from career_ai.models import (
    AIRequest,
    AIResult,
    AppConfig,
    ApplicationContent,
    Binding,
    JobEvaluation,
    JobRecord,
    ProviderAdapter,
    WorkspaceManifest,
    WorkspaceStatus,
)
from career_ai.providers import execute, provider_for
from career_ai.templates import AGENTS, COMMANDS, OPENCODE_CONFIG, SKILLS


def now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:100] or "item"


def write_json(path: Path, payload: Any, *, immutable: bool = False) -> None:
    content = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists() and path.read_text(encoding="utf-8") != content:
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.write_text(content, encoding="utf-8")


def write_text(path: Path, content: str, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists() and path.read_text(encoding="utf-8") != content:
        raise FileExistsError(f"refusing to overwrite immutable artifact: {path}")
    path.write_text(content, encoding="utf-8")


def discover_workspace(explicit: Path | None = None) -> Path:
    configured = explicit or (Path(os.environ["CAREER_AI_HOME"]) if os.environ.get("CAREER_AI_HOME") else None)
    if configured:
        candidate = configured.expanduser().resolve()
        if not (candidate / ".career-ai/workspace.json").is_file():
            raise ValueError(f"not a Career AI workspace: {candidate}")
        return candidate
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".career-ai/workspace.json").is_file():
            return candidate
    raise ValueError("workspace not found; run career-ai init or set CAREER_AI_HOME")


def relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def binding(root: Path, path: Path) -> Binding:
    if not path.is_file():
        raise ValueError(f"missing artifact: {path}")
    return Binding(path=relative(root, path), sha256=sha256_file(path))


def verify(root: Path, item: Binding) -> Path:
    path = (root / item.path).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("artifact escapes workspace")
    if not path.is_file() or sha256_file(path) != item.sha256:
        raise ValueError(f"artifact binding failed: {item.path}")
    return path


def load_manifest(root: Path) -> WorkspaceManifest:
    return WorkspaceManifest.model_validate_json(
        (root / ".career-ai/workspace.json").read_text(encoding="utf-8")
    )


def load_config(root: Path) -> AppConfig:
    return AppConfig.model_validate_json(
        (root / ".career-ai/config.json").read_text(encoding="utf-8")
    )


def require_ready(root: Path) -> WorkspaceManifest:
    manifest = load_manifest(root)
    if manifest.status is not WorkspaceStatus.READY:
        raise ValueError("workspace requires onboarding")
    assert manifest.profile and manifest.strategy
    verify(root, manifest.profile)
    verify(root, manifest.strategy)
    return manifest


def output_model(capability: str):
    return JobEvaluation if capability == "evaluate-job" else ApplicationContent


def command_init(args: argparse.Namespace) -> None:
    root = args.directory.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"target is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    stamp = now()
    manifest = WorkspaceManifest(
        workspace_id=slug(args.name),
        project_name=args.name,
        created_at=stamp,
        updated_at=stamp,
    )
    config = AppConfig(
        default_provider_id="manual-agent",
        providers=[
            {
                "provider_id": "manual-agent",
                "display_name": "Manual agent runtime",
                "adapter": "manual",
                "model": "selected-in-runtime",
                "enabled": True,
            },
            {
                "provider_id": "openai-responses",
                "display_name": "OpenAI Responses API",
                "adapter": "openai_responses",
                "model": "configure-model-id",
                "endpoint_url": "https://api.openai.com/v1/responses",
                "api_key_env": "OPENAI_API_KEY",
                "enabled": False,
                "allow_personal_data": False,
            },
            {
                "provider_id": "compatible-chat",
                "display_name": "OpenAI-compatible chat endpoint",
                "adapter": "openai_compatible_chat",
                "model": "configure-model-id",
                "endpoint_url": "https://api.example.com/v1/chat/completions",
                "api_key_env": "COMPATIBLE_API_KEY",
                "enabled": False,
                "allow_personal_data": False,
            },
        ],
    )
    write_json(root / ".career-ai/workspace.json", manifest.model_dump(mode="json"))
    write_json(root / ".career-ai/config.json", config.model_dump(mode="json"))
    schemas = {
        "job-evaluation.schema.json": JobEvaluation,
        "application-content.schema.json": ApplicationContent,
        "ai-request.schema.json": AIRequest,
        "ai-result.schema.json": AIResult,
    }
    for name, model in schemas.items():
        write_json(root / ".career-ai/schemas" / name, model.model_json_schema())
    write_text(root / "opencode.json", OPENCODE_CONFIG)
    for name, content in AGENTS.items():
        write_text(root / ".opencode/agents" / name, content)
    for name, content in COMMANDS.items():
        write_text(root / ".opencode/commands" / name, content)
    for name, content in SKILLS.items():
        write_text(root / ".agents/skills" / name, content)
    write_text(
        root / ".gitignore",
        ".env\n.env.*\nprivate/\nreports/\n*.local.json\n",
    )
    write_text(
        root / "README.md",
        f"# {args.name}\n\nPrivate Career AI workspace. Run `career-ai onboard --help`.\n",
    )
    print(json.dumps({"workspace": str(root), "status": manifest.status.value}, indent=2))


def command_onboard(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    profile_source = args.profile.expanduser().resolve()
    strategy_source = args.strategy.expanduser().resolve()
    if not profile_source.is_file() or not strategy_source.is_file():
        raise ValueError("profile and strategy files must exist")
    profile_path = root / "private/profile/master-profile.md"
    strategy_path = root / "private/profile/career-strategy.md"
    write_text(profile_path, profile_source.read_text(encoding="utf-8"))
    write_text(strategy_path, strategy_source.read_text(encoding="utf-8"))
    old = load_manifest(root)
    manifest = old.model_copy(
        update={
            "subject_name": args.name,
            "status": WorkspaceStatus.READY,
            "profile": binding(root, profile_path),
            "strategy": binding(root, strategy_path),
            "updated_at": now(),
        }
    )
    WorkspaceManifest.model_validate(manifest.model_dump())
    write_json(root / ".career-ai/workspace.json", manifest.model_dump(mode="json"))
    print(json.dumps({"status": "ready", "subject_name": args.name}, indent=2))


def command_doctor(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    checks: list[tuple[str, str]] = []
    for path in [
        ".career-ai/workspace.json",
        ".career-ai/config.json",
        ".career-ai/schemas/job-evaluation.schema.json",
        "opencode.json",
        ".opencode/agents/career-pm.md",
    ]:
        checks.append((path, "pass" if (root / path).is_file() else "fail"))
    try:
        manifest = load_manifest(root)
        config = load_config(root)
        if manifest.status is WorkspaceStatus.READY:
            require_ready(root)
        checks.append(("contracts", "pass"))
        checks.append(("providers", f"pass ({len(config.providers)})"))
    except Exception as exc:
        checks.append(("contracts", f"fail ({exc})"))
    for name, status in checks:
        print(f"[{status.upper():8}] {name}")
    if any(status.startswith("fail") for _, status in checks):
        raise SystemExit(1)


def command_status(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    manifest = load_manifest(root)
    jobs = list((root / "private/jobs/records").glob("*.json"))
    evaluations = list((root / "private/outputs").glob("*-evaluate-job-*.json"))
    applications = list((root / "private/outputs").glob("*-write-application-*.json"))
    print(f"Career AI {__version__}")
    print(f"Workspace: {manifest.project_name} [{manifest.status.value}]")
    print(f"Subject: {manifest.subject_name or 'not configured'}")
    print(f"Jobs: {len(jobs)} | Evaluations: {len(evaluations)} | Applications: {len(applications)}")
    if manifest.status is WorkspaceStatus.ONBOARDING_REQUIRED:
        print("Next: prepare profile and strategy Markdown, then run career-ai onboard")


def command_providers(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    config = load_config(root)
    payload = [
        {
            "provider_id": item.provider_id,
            "adapter": item.adapter.value,
            "model": item.model,
            "enabled": item.enabled,
            "personal_data_approved": item.allow_personal_data,
            "credential_available": bool(item.api_key_env and os.environ.get(item.api_key_env)) if item.api_key_env else None,
        }
        for item in config.providers
    ]
    print(json.dumps(payload, indent=2))


def command_runtimes(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    executable = shutil.which("opencode") or shutil.which("opencode2")
    payload = {
        "terminal": True,
        "opencode_executable": executable,
        "opencode_agents": sorted(item.stem for item in (root / ".opencode/agents").glob("*.md")),
        "skills": sorted(item.parent.name for item in (root / ".agents/skills").glob("*/SKILL.md")),
    }
    print(json.dumps(payload, indent=2))


def command_job_add(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    require_ready(root)
    source = args.file.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"vacancy file not found: {source}")
    content = source.read_text(encoding="utf-8")
    short_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    job_id = args.job_id or slug(f"{args.company}-{args.role}-{short_hash}")
    saved = root / f"private/jobs/sources/{job_id}.md"
    write_text(saved, content, immutable=True)
    record = JobRecord(
        job_id=job_id,
        company=args.company,
        role=args.role,
        source_url=args.source_url,
        source=binding(root, saved),
        captured_at=now(),
    )
    write_json(
        root / f"private/jobs/records/{job_id}.json",
        record.model_dump(mode="json"),
        immutable=True,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))


def command_job_list(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    records = []
    for path in sorted((root / "private/jobs/records").glob("*.json")):
        item = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
        records.append({"job_id": item.job_id, "company": item.company, "role": item.role})
    print(json.dumps(records, indent=2))


def build_request(
    root: Path,
    capability: str,
    job_id: str,
    provider_id: str | None,
    extra_inputs: list[Path] | None = None,
) -> tuple[AIRequest, Path, Path]:
    manifest = require_ready(root)
    assert manifest.profile and manifest.strategy
    record_path = root / f"private/jobs/records/{job_id}.json"
    record = JobRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
    source_path = verify(root, record.source)
    config = load_config(root)
    chosen_provider = provider_id or config.default_provider_id
    provider_for(config, chosen_provider)
    model = output_model(capability)
    schema_name = "job-evaluation" if capability == "evaluate-job" else "application-content"
    schema_path = root / f".career-ai/schemas/{schema_name}.schema.json"
    timestamp = now().strftime("%Y%m%d%H%M%S%f")
    request_id = slug(f"request-{timestamp}-{capability}-{job_id}")
    instructions = (
        "Evaluate the registered vacancy against verified profile evidence and explicit career strategy. "
        "Do not invent facts. Return only schema-valid JSON."
        if capability == "evaluate-job"
        else "Draft tailored CV and cover-letter text using only the bound evidence and validated decision. "
        "Preserve gaps, return only schema-valid JSON, and perform no external action."
    )
    paths = [
        verify(root, manifest.profile),
        verify(root, manifest.strategy),
        record_path,
        source_path,
        *(extra_inputs or []),
    ]
    request = AIRequest(
        request_id=request_id,
        capability=capability,
        provider_id=chosen_provider,
        instructions=instructions,
        inputs=[binding(root, path) for path in paths],
        output_schema=binding(root, schema_path),
        output_schema_name=slug(schema_name),
        created_at=now(),
    )
    request_path = root / f"private/requests/{request_id}.json"
    prompt_path = root / f"private/requests/{request_id}.prompt.md"
    write_json(request_path, request.model_dump(mode="json"), immutable=True)
    prompt = (
        f"# Career AI task: {capability}\n\n{instructions}\n\n"
        "## Bound inputs\n\n"
        + "\n".join(f"- `{item.path}` — `{item.sha256}`" for item in request.inputs)
        + f"\n\n## Output\n\nReturn only JSON matching `{request.output_schema.path}`.\n"
    )
    write_text(prompt_path, prompt, immutable=True)
    return request, request_path, prompt_path


def command_evaluate_prepare(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    request, path, prompt = build_request(root, "evaluate-job", args.job_id, args.provider)
    print(json.dumps({"request": relative(root, path), "prompt": relative(root, prompt), "provider": request.provider_id}, indent=2))


def command_application_prepare(args: argparse.Namespace) -> None:
    if not args.authorize:
        raise ValueError("application drafting requires explicit --authorize")
    root = discover_workspace(args.workspace)
    decision = args.decision.expanduser().resolve()
    if root.resolve() not in decision.parents:
        raise ValueError("decision must be inside the workspace")
    evaluation = JobEvaluation.model_validate_json(decision.read_text(encoding="utf-8"))
    if evaluation.job_id != args.job_id:
        raise ValueError("decision belongs to another job")
    if evaluation.recommendation == "reject":
        raise ValueError("rejected jobs cannot enter Application Writer")
    request, path, prompt = build_request(
        root, "write-application", args.job_id, args.provider, [decision]
    )
    print(json.dumps({"request": relative(root, path), "prompt": relative(root, prompt), "provider": request.provider_id}, indent=2))


def load_request(root: Path, path: Path) -> tuple[AIRequest, Path]:
    resolved = path if path.is_absolute() else root / path
    request = AIRequest.model_validate_json(resolved.read_text(encoding="utf-8"))
    for item in [*request.inputs, request.output_schema]:
        verify(root, item)
    return request, resolved


def persist_output(root: Path, request: AIRequest, payload: dict[str, Any]) -> Path:
    model = output_model(request.capability)
    validated = model.model_validate(payload)
    timestamp = now().strftime("%Y%m%d%H%M%S%f")
    path = root / f"private/outputs/{timestamp}-{request.capability}-{request.request_id}.json"
    write_json(path, validated.model_dump(mode="json"), immutable=True)
    return path


def persist_result(
    root: Path,
    request: AIRequest,
    request_path: Path,
    status: str,
    output: Path | None = None,
    usage=None,
    error: str | None = None,
) -> Path:
    timestamp = now().strftime("%Y%m%d%H%M%S%f")
    result = AIResult(
        result_id=slug(f"result-{timestamp}-{request.capability}"),
        request=binding(root, request_path),
        provider_id=request.provider_id,
        model=provider_for(load_config(root), request.provider_id).model,
        status=status,
        output=binding(root, output) if output else None,
        usage=usage or {},
        error=error,
        completed_at=now(),
    )
    path = root / f"private/results/{result.result_id}.json"
    write_json(path, result.model_dump(mode="json"), immutable=True)
    return path


def command_ai_run(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    request, request_path = load_request(root, args.request)
    profile = provider_for(load_config(root), request.provider_id)
    schema = json.loads(verify(root, request.output_schema).read_text(encoding="utf-8"))
    try:
        payload, usage, latency = execute(profile, request, root, schema)
        if payload is None:
            result_path = persist_result(root, request, request_path, "manual_pending")
            print(json.dumps({"status": "manual_pending", "result": relative(root, result_path)}, indent=2))
            return
        output = persist_output(root, request, payload)
        result_path = persist_result(root, request, request_path, "completed", output, usage)
        print(json.dumps({"status": "completed", "output": relative(root, output), "result": relative(root, result_path), "latency_ms": latency}, indent=2))
    except Exception as exc:
        result_path = persist_result(root, request, request_path, "failed", error=str(exc)[:1500])
        print(json.dumps({"status": "failed", "result": relative(root, result_path), "error": str(exc)}, indent=2))
        raise SystemExit(1)


def command_ai_import(args: argparse.Namespace) -> None:
    root = discover_workspace(args.workspace)
    request, request_path = load_request(root, args.request)
    source = args.output.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    output = persist_output(root, request, payload)
    result_path = persist_result(root, request, request_path, "completed", output)
    print(json.dumps({"status": "completed", "output": relative(root, output), "result": relative(root, result_path)}, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--version", action="version", version=f"career-ai {__version__}")
    result.add_argument("--workspace", type=Path)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--name", default="My Career AI")
    init.set_defaults(handler=command_init)
    onboard = commands.add_parser("onboard")
    onboard.add_argument("--name", required=True)
    onboard.add_argument("--profile", type=Path, required=True)
    onboard.add_argument("--strategy", type=Path, required=True)
    onboard.set_defaults(handler=command_onboard)
    for name, handler in [("doctor", command_doctor), ("status", command_status), ("providers", command_providers), ("runtimes", command_runtimes)]:
        item = commands.add_parser(name)
        item.set_defaults(handler=handler)
    jobs = commands.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    add = jobs_sub.add_parser("add")
    add.add_argument("file", type=Path)
    add.add_argument("--company", required=True)
    add.add_argument("--role", required=True)
    add.add_argument("--source-url")
    add.add_argument("--job-id")
    add.set_defaults(handler=command_job_add)
    listing = jobs_sub.add_parser("list")
    listing.set_defaults(handler=command_job_list)
    evaluate = commands.add_parser("evaluate")
    eval_sub = evaluate.add_subparsers(dest="evaluate_command", required=True)
    prepare = eval_sub.add_parser("prepare")
    prepare.add_argument("job_id")
    prepare.add_argument("--provider")
    prepare.set_defaults(handler=command_evaluate_prepare)
    application = commands.add_parser("application")
    app_sub = application.add_subparsers(dest="application_command", required=True)
    app_prepare = app_sub.add_parser("prepare")
    app_prepare.add_argument("job_id")
    app_prepare.add_argument("--decision", type=Path, required=True)
    app_prepare.add_argument("--provider")
    app_prepare.add_argument("--authorize", action="store_true")
    app_prepare.set_defaults(handler=command_application_prepare)
    ai = commands.add_parser("ai")
    ai_sub = ai.add_subparsers(dest="ai_command", required=True)
    run = ai_sub.add_parser("run")
    run.add_argument("request", type=Path)
    run.set_defaults(handler=command_ai_run)
    imported = ai_sub.add_parser("import")
    imported.add_argument("request", type=Path)
    imported.add_argument("output", type=Path)
    imported.set_defaults(handler=command_ai_import)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        args.handler(args)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
