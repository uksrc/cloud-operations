"""
This module provides a clean, maintainable interface for managing
Graphiant network configurations using composition and proper separation of concerns.
"""

from typing import Optional, Dict
from .config_utils import ConfigUtils
from .interface_manager import InterfaceManager
from .backbone_manager import BackboneManager
from .bgp_manager import BGPManager
from .global_config_manager import GlobalConfigManager
from .site_manager import SiteManager
from .data_exchange_manager import DataExchangeManager
from .device_config_manager import DeviceConfigManager
from .vrrp_interface_manager import VRRPInterfaceManager
from .lag_interface_manager import LagInterfaceManager
from .site_to_site_vpn_manager import SiteToSiteVpnManager
from .static_routes_manager import StaticRoutesManager
from .ntp_manager import NtpManager
from .traffic_policy_manager import TrafficPolicyManager
from .security_policy_manager import SecurityPolicyManager
from .device_system_manager import DeviceSystemManager
from .edge_services_manager import EdgeServicesManager
from .prefix_and_port_list import PrefixAndPortListManager
from .macsec_manager import MacsecManager
from .logger import setup_logger
from .exceptions import GraphiantPlaybookError

LOG = setup_logger()


class GraphiantConfig:
    """
    Main interface for Graphiant Playbooks.

    This class provides a clean, maintainable interface for managing
    Graphiant network configurations. It uses composition to delegate
    specific responsibilities to specialized manager classes.

    The class follows the Single Responsibility Principle by delegating
    different types of configurations to appropriate managers:
    - InterfaceManager: Interface and circuit configurations
    - BGPManager: BGP peering configurations
    - GlobalConfigManager: Global configuration objects
    - SiteManager: Site management operations
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        check_mode: bool = False,
        access_token: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the GraphiantConfig class with connection parameters.

        Args:
            base_url: Base URL for the Graphiant API
            username: Username for authentication
            password: Password for authentication
            check_mode: If True, API write operations are skipped and payloads are only logged.
            access_token: Optional bearer token (e.g. from graphiant login / GRAPHIANT_ACCESS_TOKEN).
            **kwargs: Additional parameters passed to ConfigUtils
        """
        try:
            # Initialize the base utilities
            self.config_utils = ConfigUtils(
                base_url=base_url,
                username=username,
                password=password,
                check_mode=check_mode,
                access_token=access_token,
                **kwargs,
            )

            # Initialize specialized managers
            self.interfaces = InterfaceManager(self.config_utils)
            self.backbone = BackboneManager(self.config_utils)
            self.bgp = BGPManager(self.config_utils)
            self.global_config = GlobalConfigManager(self.config_utils)
            self.sites = SiteManager(self.config_utils)
            self.data_exchange = DataExchangeManager(self.config_utils)
            self.device_config = DeviceConfigManager(self.config_utils)
            self.vrrp_interfaces = VRRPInterfaceManager(self.config_utils)
            self.lag_interfaces = LagInterfaceManager(self.config_utils)
            self.site_to_site_vpn = SiteToSiteVpnManager(self.config_utils)
            self.static_routes = StaticRoutesManager(self.config_utils)
            self.ntp = NtpManager(self.config_utils)
            self.traffic_policy = TrafficPolicyManager(self.config_utils)
            self.security_policy = SecurityPolicyManager(self.config_utils)
            self.device_system = DeviceSystemManager(self.config_utils)
            self.edge_services = EdgeServicesManager(self.config_utils)
            self.prefix_port_list = PrefixAndPortListManager(self.config_utils)
            self.macsec = MacsecManager(self.config_utils)

            LOG.info("GraphiantConfig class initialized successfully with all managers")

        except Exception as e:
            LOG.error("Failed to initialize GraphiantConfig class: %s", str(e))
            raise GraphiantPlaybookError(f"GraphiantConfig initialization failed: {str(e)}")

    def get_manager_status(self) -> Dict[str, bool]:
        """
        Get the status of all managers.

        Returns:
            Dictionary indicating which managers are properly initialized
        """
        return {
            "interfaces": hasattr(self, "interfaces") and self.interfaces is not None,
            "backbone": hasattr(self, "backbone") and self.backbone is not None,
            "bgp": hasattr(self, "bgp") and self.bgp is not None,
            "global_config": hasattr(self, "global_config") and self.global_config is not None,
            "sites": hasattr(self, "sites") and self.sites is not None,
            "data_exchange": hasattr(self, "data_exchange") and self.data_exchange is not None,
            "device_config": hasattr(self, "device_config") and self.device_config is not None,
            "vrrp_interfaces": hasattr(self, "vrrp_interfaces") and self.vrrp_interfaces is not None,
            "config_utils": hasattr(self, "config_utils") and self.config_utils is not None,
            "lag_interfaces": hasattr(self, "lag_interfaces") and self.lag_interfaces is not None,
            "site_to_site_vpn": hasattr(self, "site_to_site_vpn") and self.site_to_site_vpn is not None,
            "static_routes": hasattr(self, "static_routes") and self.static_routes is not None,
            "ntp": hasattr(self, "ntp") and self.ntp is not None,
            "traffic_policy": hasattr(self, "traffic_policy") and self.traffic_policy is not None,
            "security_policy": hasattr(self, "security_policy") and self.security_policy is not None,
            "device_system": hasattr(self, "device_system") and self.device_system is not None,
            "edge_services": hasattr(self, "edge_services") and self.edge_services is not None,
            "prefix_port_list": hasattr(self, "prefix_port_list") and self.prefix_port_list is not None,
            "macsec": hasattr(self, "macsec") and self.macsec is not None,
        }
