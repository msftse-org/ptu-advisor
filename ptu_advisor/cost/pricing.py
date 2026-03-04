"""Pricing configuration for region-aware and deployment-type-aware PTU calculations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class DeploymentType(str, Enum):
    """Supported Azure OpenAI deployment pricing topologies."""

    GLOBAL = "global"
    DATA_ZONE = "data_zone"
    REGIONAL = "regional"


@dataclass(frozen=True)
class RegionConfig:
    """Region pricing multiplier configuration."""

    name: str
    display_name: str
    multiplier: float
    zone: str


@dataclass(frozen=True)
class DeploymentTypeConfig:
    """Deployment type pricing/rules configuration."""

    label: str
    base_hourly_rate: float
    increment: int
    default_min_ptu: int


REGION_CONFIGS: Dict[str, RegionConfig] = {
    "eastus": RegionConfig("eastus", "East US", 1.0, "US"),
    "eastus2": RegionConfig("eastus2", "East US 2", 1.0, "US"),
    "westus": RegionConfig("westus", "West US", 1.05, "US"),
    "westus2": RegionConfig("westus2", "West US 2", 1.0, "US"),
    "westus3": RegionConfig("westus3", "West US 3", 1.0, "US"),
    "centralus": RegionConfig("centralus", "Central US", 1.0, "US"),
    "northcentralus": RegionConfig("northcentralus", "North Central US", 1.0, "US"),
    "southcentralus": RegionConfig("southcentralus", "South Central US", 1.0, "US"),
    "canadacentral": RegionConfig("canadacentral", "Canada Central", 1.1, "Canada"),
    "canadaeast": RegionConfig("canadaeast", "Canada East", 1.1, "Canada"),
    "brazilsouth": RegionConfig("brazilsouth", "Brazil South", 1.15, "South America"),
    "northeurope": RegionConfig("northeurope", "North Europe", 1.05, "Europe"),
    "westeurope": RegionConfig("westeurope", "West Europe", 1.05, "Europe"),
    "uksouth": RegionConfig("uksouth", "UK South", 1.1, "Europe"),
    "ukwest": RegionConfig("ukwest", "UK West", 1.1, "Europe"),
    "francecentral": RegionConfig("francecentral", "France Central", 1.1, "Europe"),
    "germanywestcentral": RegionConfig("germanywestcentral", "Germany West Central", 1.1, "Europe"),
    "norwayeast": RegionConfig("norwayeast", "Norway East", 1.15, "Europe"),
    "switzerlandnorth": RegionConfig("switzerlandnorth", "Switzerland North", 1.2, "Europe"),
    "swedencentral": RegionConfig("swedencentral", "Sweden Central", 1.1, "Europe"),
    "eastasia": RegionConfig("eastasia", "East Asia", 1.1, "Asia Pacific"),
    "southeastasia": RegionConfig("southeastasia", "Southeast Asia", 1.05, "Asia Pacific"),
    "japaneast": RegionConfig("japaneast", "Japan East", 1.15, "Asia Pacific"),
    "japanwest": RegionConfig("japanwest", "Japan West", 1.15, "Asia Pacific"),
    "australiaeast": RegionConfig("australiaeast", "Australia East", 1.1, "Asia Pacific"),
    "australiasoutheast": RegionConfig("australiasoutheast", "Australia Southeast", 1.1, "Asia Pacific"),
    "koreacentral": RegionConfig("koreacentral", "Korea Central", 1.1, "Asia Pacific"),
    "koreasouth": RegionConfig("koreasouth", "Korea South", 1.1, "Asia Pacific"),
    "centralindia": RegionConfig("centralindia", "Central India", 1.05, "India"),
    "southindia": RegionConfig("southindia", "South India", 1.05, "India"),
    "westindia": RegionConfig("westindia", "West India", 1.05, "India"),
    "uaenorth": RegionConfig("uaenorth", "UAE North", 1.15, "Middle East"),
    "southafricanorth": RegionConfig("southafricanorth", "South Africa North", 1.2, "Africa"),
    "qatarcentral": RegionConfig("qatarcentral", "Qatar Central", 1.15, "Middle East"),
    "polandcentral": RegionConfig("polandcentral", "Poland Central", 1.1, "Europe"),
}


DEPLOYMENT_TYPE_CONFIGS: Dict[DeploymentType, DeploymentTypeConfig] = {
    DeploymentType.GLOBAL: DeploymentTypeConfig(
        label="Global",
        base_hourly_rate=1.00,
        increment=5,
        default_min_ptu=15,
    ),
    DeploymentType.DATA_ZONE: DeploymentTypeConfig(
        label="Data Zone",
        base_hourly_rate=1.10,
        increment=5,
        default_min_ptu=15,
    ),
    DeploymentType.REGIONAL: DeploymentTypeConfig(
        label="Regional",
        base_hourly_rate=2.00,
        increment=50,
        default_min_ptu=50,
    ),
}


def normalize_region(region: str) -> str:
    """Normalize user-provided region strings to canonical keys."""

    value = (region or "").strip().lower().replace(" ", "")
    return value or "eastus"


def get_region_config(region: str) -> RegionConfig:
    """Return known region config; fallback to East US defaults."""

    key = normalize_region(region)
    return REGION_CONFIGS.get(key, REGION_CONFIGS["eastus"])


def get_deployment_type(value: str) -> DeploymentType:
    """Parse deployment type with a safe fallback."""

    raw = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw == DeploymentType.DATA_ZONE.value:
        return DeploymentType.DATA_ZONE
    if raw == DeploymentType.REGIONAL.value:
        return DeploymentType.REGIONAL
    return DeploymentType.GLOBAL


def get_deployment_config(value: str) -> DeploymentTypeConfig:
    """Get deployment pricing config for the given type."""

    deployment_type = get_deployment_type(value)
    return DEPLOYMENT_TYPE_CONFIGS[deployment_type]
