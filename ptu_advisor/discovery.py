"""Azure resource discovery for PTU Advisor dashboard.

Provides cached, Streamlit-friendly functions to discover Azure subscriptions,
Cognitive Services / AI Services accounts, and model deployments — so the
dashboard can present cascading dropdowns with zero manual typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from azure.core.credentials import TokenCredential


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UserInfo:
    """Authenticated user identity."""

    display_name: str
    tenant_id: str
    email: str = ""


@dataclass
class SubscriptionInfo:
    """An Azure subscription the user has access to."""

    subscription_id: str
    display_name: str
    state: str  # e.g. "Enabled"

    @property
    def label(self) -> str:
        """Human-readable label for dropdown display."""
        short_id = self.subscription_id[:8]
        return f"{self.display_name} ({short_id}…)"


@dataclass
class AccountInfo:
    """A Cognitive Services / AI Services account."""

    name: str
    resource_group: str
    location: str
    kind: str  # e.g. "OpenAI", "AIServices", "CognitiveServices"
    sku_name: str = ""

    @property
    def label(self) -> str:
        """Human-readable label for dropdown display."""
        return f"{self.name}  ({self.resource_group})"


# Re-export DeploymentInfo from models so callers only need this module.
from ptu_advisor.metrics.models import DeploymentInfo  # noqa: E402


# ---------------------------------------------------------------------------
# SDK availability check
# ---------------------------------------------------------------------------

_INSTALL_HINT = (
    "Azure SDK packages are required for live connection. Run:\n\n"
    "```\n"
    "pip install azure-identity azure-mgmt-subscription "
    "azure-mgmt-cognitiveservices azure-mgmt-monitor\n"
    "```"
)


def azure_sdk_available() -> bool:
    """Return True if the required Azure SDK packages are importable."""
    try:
        import azure.identity  # noqa: F401
        import azure.mgmt.subscription  # noqa: F401
        import azure.mgmt.cognitiveservices  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate() -> Tuple[TokenCredential, UserInfo]:
    """Authenticate using the local Azure CLI credential chain.

    Returns:
        (credential, user_info) — credential can be reused for all ARM calls;
        user_info contains the signed-in user's display name and tenant.

    Raises:
        ptu_advisor.auth.AuthenticationError on failure.
    """
    from ptu_advisor.auth import get_azure_credential

    credential = get_azure_credential()

    # Decode the JWT access token to extract user identity.
    user_info = _extract_user_info(credential)

    return credential, user_info


def _extract_user_info(credential: TokenCredential) -> UserInfo:
    """Best-effort extraction of display name / email from the ARM token."""
    import json
    import base64

    try:
        token = credential.get_token("https://management.azure.com/.default")
        # JWT has 3 dot-separated parts; the payload is part [1].
        payload_b64 = token.token.split(".")[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return UserInfo(
            display_name=payload.get("name", payload.get("upn", "Azure User")),
            email=payload.get("upn", payload.get("email", "")),
            tenant_id=payload.get("tid", ""),
        )
    except Exception:
        return UserInfo(display_name="Azure User", tenant_id="", email="")


# ---------------------------------------------------------------------------
# Subscription discovery
# ---------------------------------------------------------------------------

def list_subscriptions(credential: TokenCredential) -> List[SubscriptionInfo]:
    """List all Azure subscriptions accessible by the credential.

    Returns subscriptions sorted by display name.  Enabled subscriptions
    appear first.
    """
    from azure.mgmt.subscription import SubscriptionClient

    client = SubscriptionClient(credential)
    subs: List[SubscriptionInfo] = []

    for s in client.subscriptions.list():
        subs.append(
            SubscriptionInfo(
                subscription_id=s.subscription_id,
                display_name=s.display_name or s.subscription_id,
                state=s.state or "Unknown",
            )
        )

    # Sort: enabled first, then alphabetical.
    subs.sort(key=lambda x: (x.state != "Enabled", x.display_name.lower()))
    return subs


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------

def list_ai_accounts(
    credential: TokenCredential,
    subscription_id: str,
) -> List[AccountInfo]:
    """List all Cognitive Services / AI Services accounts in a subscription.

    Returns accounts sorted by name, filtered to relevant kinds
    (OpenAI, AIServices, CognitiveServices).
    """
    from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient

    client = CognitiveServicesManagementClient(credential, subscription_id)
    accounts: List[AccountInfo] = []

    # .list() iterates across ALL resource groups in the subscription.
    for acct in client.accounts.list():
        # Extract resource group from the resource ID
        # Format: /subscriptions/.../resourceGroups/<RG>/providers/...
        rg = _extract_resource_group(acct.id) if acct.id else ""

        kind = acct.kind or ""
        # Only include AI-relevant kinds
        if kind.lower() in ("openai", "aiservices", "cognitiveservices", "internal"):
            accounts.append(
                AccountInfo(
                    name=acct.name or "",
                    resource_group=rg,
                    location=acct.location or "",
                    kind=kind,
                    sku_name=acct.sku.name if acct.sku else "",
                )
            )

    accounts.sort(key=lambda a: a.name.lower())
    return accounts


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an Azure resource ID."""
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("resourcegroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Deployment discovery
# ---------------------------------------------------------------------------

def list_deployments(
    credential: TokenCredential,
    subscription_id: str,
    resource_group: str,
    account_name: str,
) -> List[DeploymentInfo]:
    """List all model deployments in a Cognitive Services account.

    Wraps the existing ``list_workspace_deployments`` collector function
    for API consistency within this module.
    """
    from ptu_advisor.metrics.collector import list_workspace_deployments

    return list_workspace_deployments(
        credential=credential,
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace=account_name,
    )
