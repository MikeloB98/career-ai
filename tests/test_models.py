from __future__ import annotations

from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from career_ai.models import AIResult, AppConfig, ProviderProfile, WorkspaceManifest


class ModelTests(unittest.TestCase):
    def test_ready_workspace_requires_profile_and_strategy(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires subject"):
            WorkspaceManifest(
                workspace_id="test-workspace",
                project_name="Test",
                subject_name="Alex",
                status="ready",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

    def test_provider_config_contains_no_credential_value(self) -> None:
        provider = ProviderProfile(
            provider_id="openai-test",
            display_name="OpenAI",
            adapter="openai_responses",
            model="model-id",
            endpoint_url="https://api.openai.com/v1/responses",
            api_key_env="OPENAI_API_KEY",
        )
        config = AppConfig(default_provider_id="openai-test", providers=[provider])
        self.assertNotIn("sk-", config.model_dump_json())

    def test_duplicate_provider_ids_are_rejected(self) -> None:
        provider = ProviderProfile(
            provider_id="manual-test",
            display_name="Manual",
            adapter="manual",
            model="selected",
        )
        with self.assertRaisesRegex(ValidationError, "unique"):
            AppConfig(default_provider_id="manual-test", providers=[provider, provider])

    def test_remote_provider_requires_https(self) -> None:
        with self.assertRaisesRegex(ValidationError, "HTTPS"):
            ProviderProfile(
                provider_id="unsafe-test",
                display_name="Unsafe",
                adapter="openai_compatible_chat",
                model="model",
                endpoint_url="http://example.com/v1/chat/completions",
                api_key_env="UNSAFE_API_KEY",
            )

    def test_completed_result_requires_output(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires output"):
            AIResult(
                result_id="result-test-complete",
                request={"path": "request.json", "sha256": "0" * 64},
                provider_id="manual-test",
                model="model",
                status="completed",
                completed_at=datetime.now(timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
