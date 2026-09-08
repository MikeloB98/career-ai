from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from career_ai.cli import (
    binding,
    build_request,
    command_application_prepare,
    command_init,
    command_job_add,
    command_onboard,
    discover_workspace,
    load_manifest,
    persist_output,
    require_ready,
    verify,
)
from career_ai.models import AppConfig, JobEvaluation, ProviderProfile, WorkspaceStatus
from career_ai.providers import execute


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def build_workspace(self, directory: Path) -> Path:
        workspace = directory / "workspace"
        command_init(Namespace(directory=workspace, name="Synthetic Career"))
        profile = ROOT / "examples/synthetic/profile.md"
        strategy = ROOT / "examples/synthetic/strategy.md"
        command_onboard(
            Namespace(
                workspace=workspace,
                name="Alex Rivera",
                profile=profile,
                strategy=strategy,
            )
        )
        return workspace

    def test_complete_manual_vertical_slice(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            workspace = self.build_workspace(directory)
            manifest = require_ready(workspace)
            self.assertEqual(manifest.status, WorkspaceStatus.READY)
            command_job_add(
                Namespace(
                    workspace=workspace,
                    file=ROOT / "examples/synthetic/vacancy.md",
                    company="Example Manufacturing",
                    role="Materials Engineer",
                    source_url="https://example.com/jobs/materials",
                    job_id="synthetic-materials-role",
                )
            )
            request, request_path, prompt_path = build_request(
                workspace,
                "evaluate-job",
                "synthetic-materials-role",
                None,
            )
            self.assertTrue(prompt_path.is_file())
            self.assertEqual(request.provider_id, "manual-agent")
            evaluation_payload = json.loads(
                (ROOT / "examples/synthetic/evaluation.json").read_text(encoding="utf-8")
            )
            evaluation_path = persist_output(workspace, request, evaluation_payload)
            evaluation = JobEvaluation.model_validate_json(
                evaluation_path.read_text(encoding="utf-8")
            )
            self.assertEqual(evaluation.recommendation, "apply")
            command_application_prepare(
                Namespace(
                    workspace=workspace,
                    job_id="synthetic-materials-role",
                    decision=evaluation_path,
                    provider=None,
                    authorize=True,
                )
            )
            app_requests = list((workspace / "private/requests").glob("*write-application*.json"))
            self.assertEqual(len(app_requests), 1)
            self.assertTrue(request_path.is_file())

    def test_tampered_profile_binding_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = self.build_workspace(Path(raw))
            manifest = load_manifest(workspace)
            assert manifest.profile
            profile_path = workspace / manifest.profile.path
            profile_path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "binding failed"):
                require_ready(workspace)

    def test_rejected_decision_cannot_start_writer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = self.build_workspace(Path(raw))
            command_job_add(
                Namespace(
                    workspace=workspace,
                    file=ROOT / "examples/synthetic/vacancy.md",
                    company="Example Manufacturing",
                    role="Materials Engineer",
                    source_url=None,
                    job_id="synthetic-materials-role",
                )
            )
            payload = json.loads(
                (ROOT / "examples/synthetic/evaluation.json").read_text(encoding="utf-8")
            )
            payload["recommendation"] = "reject"
            decision = workspace / "private/rejected.json"
            decision.parent.mkdir(parents=True, exist_ok=True)
            decision.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot enter"):
                command_application_prepare(
                    Namespace(
                        workspace=workspace,
                        job_id="synthetic-materials-role",
                        decision=decision,
                        provider=None,
                        authorize=True,
                    )
                )

    def test_http_provider_blocks_personal_data_by_default(self) -> None:
        profile = ProviderProfile(
            provider_id="external-test",
            display_name="External",
            adapter="openai_responses",
            model="test-model",
            endpoint_url="https://api.example.com/v1/responses",
            api_key_env="EXTERNAL_TEST_KEY",
            enabled=True,
            allow_personal_data=False,
        )
        with tempfile.TemporaryDirectory() as raw:
            workspace = self.build_workspace(Path(raw))
            command_job_add(
                Namespace(
                    workspace=workspace,
                    file=ROOT / "examples/synthetic/vacancy.md",
                    company="Example Manufacturing",
                    role="Materials Engineer",
                    source_url=None,
                    job_id="synthetic-materials-role",
                )
            )
            request, _, _ = build_request(
                workspace, "evaluate-job", "synthetic-materials-role", None
            )
            schema = JobEvaluation.model_json_schema()
            with self.assertRaisesRegex(ValueError, "not approved for personal data"):
                execute(profile, request, workspace, schema)

    def test_workspace_discovery_walks_upward(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            command_init(Namespace(directory=workspace, name="Discovery"))
            nested = workspace / "a/b"
            nested.mkdir(parents=True)
            with patch("pathlib.Path.cwd", return_value=nested):
                self.assertEqual(discover_workspace(), workspace.resolve())


if __name__ == "__main__":
    unittest.main()
