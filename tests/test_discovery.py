"""Tests for ptu_advisor.discovery — Azure resource auto-discovery logic."""

import base64
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from ptu_advisor.discovery import (
    AccountInfo,
    SubscriptionInfo,
    UserInfo,
    _extract_resource_group,
    _extract_user_info,
    azure_sdk_available,
    list_ai_accounts,
    list_subscriptions,
    _credential_cache_key,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_jwt_payload(payload: dict) -> str:
    """Build a minimal JWT (header.payload.signature) with given payload dict."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fake-sig"


def _make_token(payload: dict) -> SimpleNamespace:
    """Return an object that looks like azure.core.credentials.AccessToken."""
    return SimpleNamespace(token=_make_jwt_payload(payload))


# ============================================================================
# Data classes
# ============================================================================


class TestUserInfo:
    def test_defaults(self):
        u = UserInfo(display_name="Alice", tenant_id="t-1")
        assert u.display_name == "Alice"
        assert u.tenant_id == "t-1"
        assert u.email == ""

    def test_with_email(self):
        u = UserInfo(display_name="Bob", tenant_id="t-2", email="bob@contoso.com")
        assert u.email == "bob@contoso.com"


class TestSubscriptionInfo:
    def test_label_format(self):
        s = SubscriptionInfo(
            subscription_id="abcdefgh-1234-5678-9abc-def012345678",
            display_name="My Sub",
            state="Enabled",
        )
        assert s.label == "My Sub (abcdefgh…)"

    def test_label_short_id(self):
        """ID shorter than 8 chars should not crash."""
        s = SubscriptionInfo(subscription_id="abc", display_name="S", state="Enabled")
        assert s.label == "S (abc…)"


class TestAccountInfo:
    def test_label_format(self):
        a = AccountInfo(
            name="my-oai",
            resource_group="rg-foo",
            location="eastus",
            kind="OpenAI",
        )
        assert a.label == "my-oai  (rg-foo)"

    def test_optional_sku(self):
        a = AccountInfo(
            name="x", resource_group="rg", location="west", kind="AIServices"
        )
        assert a.sku_name == ""


# ============================================================================
# _extract_resource_group
# ============================================================================


class TestExtractResourceGroup:
    def test_valid_resource_id(self):
        rid = (
            "/subscriptions/00000000-0000-0000-0000-000000000000"
            "/resourceGroups/my-rg"
            "/providers/Microsoft.CognitiveServices/accounts/my-oai"
        )
        assert _extract_resource_group(rid) == "my-rg"

    def test_case_insensitive(self):
        rid = (
            "/subscriptions/sub123/RESOURCEGROUPS/RG-Upper"
            "/providers/Microsoft.CognitiveServices/accounts/x"
        )
        assert _extract_resource_group(rid) == "RG-Upper"

    def test_missing_segment(self):
        assert _extract_resource_group("/subscriptions/sub123/providers/x") == ""

    def test_empty_string(self):
        assert _extract_resource_group("") == ""

    def test_no_value_after_resourcegroups(self):
        """resourceGroups at the end with no following segment."""
        assert _extract_resource_group("/subscriptions/sub/resourceGroups") == ""


# ============================================================================
# _extract_user_info  (JWT decoding)
# ============================================================================


class TestExtractUserInfo:
    def test_full_payload(self):
        cred = MagicMock()
        cred.get_token.return_value = _make_token(
            {"name": "Alice", "upn": "alice@contoso.com", "tid": "tenant-1"}
        )
        info = _extract_user_info(cred)
        assert info.display_name == "Alice"
        assert info.email == "alice@contoso.com"
        assert info.tenant_id == "tenant-1"

    def test_name_falls_back_to_upn(self):
        cred = MagicMock()
        cred.get_token.return_value = _make_token({"upn": "bob@contoso.com"})
        info = _extract_user_info(cred)
        assert info.display_name == "bob@contoso.com"

    def test_email_falls_back_to_email_field(self):
        """When 'upn' is missing, fall back to 'email' field."""
        cred = MagicMock()
        cred.get_token.return_value = _make_token(
            {"name": "Charlie", "email": "c@contoso.com", "tid": "t"}
        )
        info = _extract_user_info(cred)
        assert info.email == "c@contoso.com"

    def test_fallback_on_malformed_token(self):
        """Completely broken token → returns safe defaults."""
        cred = MagicMock()
        cred.get_token.return_value = SimpleNamespace(token="not-a-jwt")
        info = _extract_user_info(cred)
        assert info.display_name == "Azure User"
        assert info.tenant_id == ""

    def test_fallback_on_get_token_exception(self):
        cred = MagicMock()
        cred.get_token.side_effect = Exception("auth expired")
        info = _extract_user_info(cred)
        assert info.display_name == "Azure User"

    def test_missing_all_fields(self):
        """Token with empty payload → safe fallbacks."""
        cred = MagicMock()
        cred.get_token.return_value = _make_token({})
        info = _extract_user_info(cred)
        assert info.display_name == "Azure User"
        assert info.email == ""
        assert info.tenant_id == ""


def test_credential_cache_key_falls_back_to_full_token_when_identity_claims_missing():
    first = MagicMock()
    second = MagicMock()
    first.get_token.return_value = _make_token({"nonce": "one"})
    second.get_token.return_value = _make_token({"nonce": "two"})

    assert _credential_cache_key(first) != _credential_cache_key(second)


# ============================================================================
# azure_sdk_available
# ============================================================================


class TestAzureSdkAvailable:
    def test_true_when_packages_exist(self):
        # Packages are installed in this env, so this should be True.
        # If not installed, this test is skipped via the mark below.
        result = azure_sdk_available()
        if result:
            assert result is True
        else:
            pytest.skip("Azure SDK not installed in test environment")

    @patch.dict("sys.modules", {"azure.identity": None})
    def test_false_when_identity_missing(self):
        """Simulating ImportError on azure.identity."""
        # Patching sys.modules with None causes ImportError on import.
        assert azure_sdk_available() is False


# ============================================================================
# list_subscriptions
# ============================================================================


def _mock_subscription(sub_id: str, name: str, state: str = "Enabled"):
    """Create a mock that looks like azure.mgmt.subscription.models.Subscription."""
    s = SimpleNamespace()
    s.subscription_id = sub_id
    s.display_name = name
    s.state = state
    return s


class TestListSubscriptions:
    @patch("azure.mgmt.subscription.SubscriptionClient")
    def test_basic_listing(self, MockSubClient):
        client_instance = MagicMock()
        MockSubClient.return_value = client_instance
        client_instance.subscriptions.list.return_value = [
            _mock_subscription("id-1", "Sub A"),
            _mock_subscription("id-2", "Sub B"),
        ]

        cred = MagicMock()
        result = list_subscriptions(cred)

        assert len(result) == 2
        assert result[0].display_name == "Sub A"
        assert result[1].display_name == "Sub B"
        MockSubClient.assert_called_once_with(cred)

    @patch("azure.mgmt.subscription.SubscriptionClient")
    def test_enabled_first_sorting(self, MockSubClient):
        client_instance = MagicMock()
        MockSubClient.return_value = client_instance
        client_instance.subscriptions.list.return_value = [
            _mock_subscription("id-1", "Zulu", state="Disabled"),
            _mock_subscription("id-2", "Alpha", state="Enabled"),
            _mock_subscription("id-3", "Beta", state="Enabled"),
        ]

        result = list_subscriptions(MagicMock())

        assert result[0].display_name == "Alpha"  # Enabled, first alphabetically
        assert result[1].display_name == "Beta"  # Enabled, second
        assert result[2].display_name == "Zulu"  # Disabled, last

    @patch("azure.mgmt.subscription.SubscriptionClient")
    def test_empty_list(self, MockSubClient):
        client_instance = MagicMock()
        MockSubClient.return_value = client_instance
        client_instance.subscriptions.list.return_value = []

        result = list_subscriptions(MagicMock())
        assert result == []

    @patch("azure.mgmt.subscription.SubscriptionClient")
    def test_none_display_name_fallback(self, MockSubClient):
        """display_name=None should fall back to subscription_id."""
        client_instance = MagicMock()
        MockSubClient.return_value = client_instance
        sub = SimpleNamespace(
            subscription_id="fallback-id", display_name=None, state=None
        )
        client_instance.subscriptions.list.return_value = [sub]

        result = list_subscriptions(MagicMock())
        assert result[0].display_name == "fallback-id"
        assert result[0].state == "Unknown"


# ============================================================================
# list_ai_accounts
# ============================================================================


def _mock_account(
    name: str,
    kind: str,
    resource_id: str = "",
    location: str = "eastus",
    sku_name: str = "S0",
):
    """Create a mock that looks like a Cognitive Services Account."""
    acct = SimpleNamespace()
    acct.name = name
    acct.kind = kind
    acct.id = resource_id or (
        f"/subscriptions/sub-1/resourceGroups/rg-{name}"
        f"/providers/Microsoft.CognitiveServices/accounts/{name}"
    )
    acct.location = location
    acct.sku = SimpleNamespace(name=sku_name)
    return acct


class TestListAiAccounts:
    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_filters_relevant_kinds(self, MockCSClient):
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        client_instance.accounts.list.return_value = [
            _mock_account("oai-1", "OpenAI"),
            _mock_account("ai-svc", "AIServices"),
            _mock_account("cog-svc", "CognitiveServices"),
            _mock_account("internal-1", "Internal"),
            _mock_account("search-1", "Search"),  # Should be excluded
            _mock_account("form-1", "FormRecognizer"),  # Should be excluded
        ]

        cred = MagicMock()
        result = list_ai_accounts(cred, "sub-1")

        names = [a.name for a in result]
        assert "oai-1" in names
        assert "ai-svc" in names
        assert "cog-svc" in names
        assert "internal-1" in names
        assert "search-1" not in names
        assert "form-1" not in names

    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_sorts_by_name(self, MockCSClient):
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        client_instance.accounts.list.return_value = [
            _mock_account("zebra", "OpenAI"),
            _mock_account("alpha", "OpenAI"),
            _mock_account("mango", "AIServices"),
        ]

        result = list_ai_accounts(MagicMock(), "sub-1")
        assert [a.name for a in result] == ["alpha", "mango", "zebra"]

    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_extracts_resource_group(self, MockCSClient):
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        client_instance.accounts.list.return_value = [
            _mock_account(
                "oai-x",
                "OpenAI",
                resource_id=(
                    "/subscriptions/sub-1/resourceGroups/my-special-rg"
                    "/providers/Microsoft.CognitiveServices/accounts/oai-x"
                ),
            ),
        ]

        result = list_ai_accounts(MagicMock(), "sub-1")
        assert result[0].resource_group == "my-special-rg"

    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_empty_kind_excluded(self, MockCSClient):
        """Account with empty kind string should be excluded."""
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        client_instance.accounts.list.return_value = [
            _mock_account("no-kind", ""),
        ]

        result = list_ai_accounts(MagicMock(), "sub-1")
        assert len(result) == 0

    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_none_fields_handled(self, MockCSClient):
        """Account with None name / location / sku should not crash."""
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        acct = SimpleNamespace(
            name=None,
            kind="OpenAI",
            id="/subscriptions/s/resourceGroups/rg/providers/X/accounts/x",
            location=None,
            sku=None,
        )
        client_instance.accounts.list.return_value = [acct]

        result = list_ai_accounts(MagicMock(), "sub-1")
        assert len(result) == 1
        assert result[0].name == ""
        assert result[0].location == ""
        assert result[0].sku_name == ""

    @patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient")
    def test_kind_is_case_insensitive(self, MockCSClient):
        """Kind comparison should be case-insensitive."""
        client_instance = MagicMock()
        MockCSClient.return_value = client_instance
        client_instance.accounts.list.return_value = [
            _mock_account("upper", "OPENAI"),
            _mock_account("mixed", "AiServices"),
        ]

        result = list_ai_accounts(MagicMock(), "sub-1")
        assert len(result) == 2


# ============================================================================
# list_deployments (thin wrapper over collector)
# ============================================================================


class TestListDeployments:
    @patch("ptu_advisor.metrics.collector.list_workspace_deployments")
    def test_passes_through_to_collector(self, mock_lwd):
        from ptu_advisor.discovery import list_deployments

        sentinel = [MagicMock()]
        mock_lwd.return_value = sentinel

        cred = MagicMock()
        result = list_deployments(cred, "sub-1", "rg-x", "acct-y")

        mock_lwd.assert_called_once_with(
            credential=cred,
            subscription_id="sub-1",
            resource_group="rg-x",
            workspace="acct-y",
        )
        assert result is sentinel


# ============================================================================
# authenticate (integration-like, fully mocked)
# ============================================================================


class TestAuthenticate:
    @patch("ptu_advisor.discovery._extract_user_info")
    @patch("ptu_advisor.auth.get_azure_credential")
    def test_returns_credential_and_user_info(self, mock_get_cred, mock_extract):
        from ptu_advisor.discovery import authenticate

        fake_cred = MagicMock()
        fake_user = UserInfo(display_name="Test", tenant_id="t-1")
        mock_get_cred.return_value = fake_cred
        mock_extract.return_value = fake_user

        cred, user = authenticate()

        assert cred is fake_cred
        assert user is fake_user
        mock_get_cred.assert_called_once()
        mock_extract.assert_called_once_with(fake_cred)
