"""Tests for Azure auth utilities."""

from unittest.mock import MagicMock, patch

import pytest

from ptu_advisor.auth import AuthenticationError, get_azure_credential, get_subscription_id


class TestGetAzureCredential:
    """Tests for credential construction and validation."""

    def test_returns_chained_credential_when_token_fetch_succeeds(self):
        fake_credential = MagicMock()
        fake_credential.get_token.return_value = MagicMock(token="ok")

        with patch("ptu_advisor.auth.ChainedTokenCredential", return_value=fake_credential):
            credential = get_azure_credential()

        assert credential is fake_credential
        fake_credential.get_token.assert_called_once_with("https://management.azure.com/.default")

    def test_raises_authentication_error_when_token_fetch_fails(self):
        fake_credential = MagicMock()
        fake_credential.get_token.side_effect = RuntimeError("auth failed")

        with patch("ptu_advisor.auth.ChainedTokenCredential", return_value=fake_credential):
            with pytest.raises(AuthenticationError):
                get_azure_credential()


class TestGetSubscriptionId:
    """Tests for subscription selection."""

    def test_returns_explicit_subscription_id(self):
        credential = MagicMock()
        result = get_subscription_id(credential, "explicit-sub")
        assert result == "explicit-sub"

    def test_returns_env_subscription_id_if_present(self, monkeypatch):
        monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "env-sub")
        credential = MagicMock()
        result = get_subscription_id(credential)
        assert result == "env-sub"

    def test_prefers_enabled_subscription(self, monkeypatch):
        monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)

        sub_disabled = MagicMock(subscription_id="sub-disabled", state="Disabled")
        sub_enabled = MagicMock(subscription_id="sub-enabled", state="Enabled")

        mock_client = MagicMock()
        mock_client.subscriptions.list.return_value = [sub_disabled, sub_enabled]

        with patch("ptu_advisor.auth.SubscriptionClient", return_value=mock_client):
            result = get_subscription_id(MagicMock())

        assert result == "sub-enabled"
