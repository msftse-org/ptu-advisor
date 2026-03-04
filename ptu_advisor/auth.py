"""Azure authentication utilities for PTU Advisor."""

from __future__ import annotations

import os
from typing import Optional

from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)
from azure.core.credentials import TokenCredential

try:
    from azure.mgmt.resource import SubscriptionClient  # type: ignore
except Exception:
    try:
        from azure.mgmt.subscription import SubscriptionClient  # type: ignore
    except Exception:
        SubscriptionClient = None  # type: ignore[assignment]

from ptu_advisor.config import AnalysisConfig


class AuthenticationError(Exception):
    """Raised when Azure authentication fails."""
    pass


class AccessValidationError(Exception):
    """Raised when the user doesn't have access to the specified resources."""
    pass


def get_azure_credential() -> TokenCredential:
    """
    Get Azure credential using Azure CLI authentication.
    
    This uses a deterministic credential chain:
    1. DefaultAzureCredential (managed identity, workload identity, env creds)
    2. AzureCliCredential (local development fallback)
    
    Returns:
        TokenCredential: Azure credential for API calls.
        
    Raises:
        AuthenticationError: If authentication fails.
    """
    try:
        # Prefer Azure SDK defaults (cloud/runtime), then CLI for local dev.
        credential = ChainedTokenCredential(
            DefaultAzureCredential(exclude_interactive_browser_credential=True),
            AzureCliCredential(),
            ManagedIdentityCredential(),
        )
        
        # Validate the credential works by getting a token
        # Use Azure Resource Manager scope for validation
        credential.get_token("https://management.azure.com/.default")
        
        return credential
        
    except Exception as e:
        raise AuthenticationError(
            f"Failed to authenticate with Azure. "
            f"Please run 'az login' first.\n"
            f"Error: {e}"
        ) from e


def get_subscription_id(
    credential: TokenCredential,
    subscription_id: Optional[str] = None,
) -> str:
    """
    Get the subscription ID to use.
    
    Args:
        credential: Azure credential.
        subscription_id: Optional explicit subscription ID.
        
    Returns:
        Subscription ID to use for API calls.
        
    Raises:
        AccessValidationError: If no subscription is accessible.
    """
    if subscription_id:
        return subscription_id

    env_subscription = os.getenv("AZURE_SUBSCRIPTION_ID")
    if env_subscription:
        return env_subscription
    
    try:
        if SubscriptionClient is None:
            raise AccessValidationError(
                "Azure subscription client is unavailable. Provide --subscription "
                "or set AZURE_SUBSCRIPTION_ID."
            )

        # Get the default subscription from Azure CLI
        client = SubscriptionClient(credential)
        subscriptions = list(client.subscriptions.list())
        
        if not subscriptions:
            raise AccessValidationError(
                "No Azure subscriptions found. "
                "Please ensure your account has access to at least one subscription."
            )
        
        # Prefer an enabled subscription when available.
        enabled_subscriptions = [
            sub for sub in subscriptions if getattr(sub, "state", "") == "Enabled"
        ]
        preferred = enabled_subscriptions[0] if enabled_subscriptions else subscriptions[0]
        return preferred.subscription_id
        
    except Exception as e:
        raise AccessValidationError(
            f"Failed to get subscription information: {e}"
        ) from e


def validate_access(
    credential: TokenCredential,
    config: AnalysisConfig,
) -> None:
    """
    Validate that the user has access to the specified resources.
    
    Args:
        credential: Azure credential.
        config: Analysis configuration with resource identifiers.
        
    Raises:
        AccessValidationError: If access validation fails.
    """
    from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
    
    # Get subscription ID
    subscription_id = get_subscription_id(credential, config.subscription_id)
    
    try:
        # Validate access to the Cognitive Services account (Foundry workspace)
        client = CognitiveServicesManagementClient(credential, subscription_id)
        
        # Try to get the account - this will fail if no access
        account = client.accounts.get(
            resource_group_name=config.resource_group,
            account_name=config.workspace,
        )
        
        if not account:
            raise AccessValidationError(
                f"Workspace '{config.workspace}' not found in resource group "
                f"'{config.resource_group}'."
            )
            
    except AccessValidationError:
        raise
    except Exception as e:
        raise AccessValidationError(
            f"Failed to access workspace '{config.workspace}' in resource group "
            f"'{config.resource_group}'. Please check:\n"
            f"  1. The workspace name and resource group are correct\n"
            f"  2. You have at least Reader access to the resource\n"
            f"  3. The subscription ID is correct (if specified)\n"
            f"Error: {e}"
        ) from e


def get_resource_id(
    subscription_id: str,
    resource_group: str,
    workspace: str,
    deployment: Optional[str] = None,
) -> str:
    """
    Construct the Azure resource ID for a Foundry resource.
    
    Args:
        subscription_id: Azure subscription ID.
        resource_group: Resource group name.
        workspace: Foundry workspace name.
        deployment: Optional deployment name.
        
    Returns:
        Full Azure resource ID string.
    """
    base_id = (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices"
        f"/accounts/{workspace}"
    )
    
    if deployment:
        return f"{base_id}/deployments/{deployment}"
    
    return base_id
