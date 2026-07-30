"""
This module provides standardized utility methods for building configuration payloads
using Jinja2 templates. All methods follow consistent patterns for better maintainability.
"""

from .portal_utils import PortalUtils
from .config_templates import ConfigTemplates
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()


class ConfigUtils(PortalUtils):
    """
    Standardized utility class for building device configuration payloads.

    This class provides consistent methods for rendering templates and updating
    configuration payloads with proper error handling and logging.
    """

    def __init__(self, base_url=None, username=None, password=None, access_token=None, **kwargs):
        """Initialize ConfigUtils with portal connection and template renderer."""
        super().__init__(base_url=base_url, username=username, password=password, access_token=access_token, **kwargs)
        self.template = ConfigTemplates(self.template_path)

    def _validate_required_params(self, kwargs, required_params):
        """
        Validate that required parameters are present.

        Args:
            kwargs: Dictionary of parameters to validate
            required_params: List of required parameter names

        Raises:
            ConfigurationError: If any required parameters are missing
        """
        missing_params = [param for param in required_params if param not in kwargs]
        if missing_params:
            raise ConfigurationError(f"Missing required parameters: {missing_params}")

    def global_prefix_set(self, config_payload, action="add", **kwargs):
        """
        Update the global_prefix_sets section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global prefix set: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_global_prefix_set(action=action, **kwargs)
            if action == "add":
                config_payload["global_prefix_sets"].update(result)
            else:  # delete
                config_payload["global_prefix_sets"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global prefix set %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global prefix set processing failed: {str(e)}")

    def global_bgp_filter(self, config_payload, action="add", **kwargs):
        """
        Update the routing_policies section of the configuration payload.

        Args:
            config_payload (dict): The configuration dictionary that holds routing policies.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional parameters used for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global BGP filter: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_global_bgp_filter(action=action, **kwargs)
            if action == "add":
                config_payload["routing_policies"].update(result)
            else:  # delete
                config_payload["routing_policies"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global BGP filter %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global BGP filter processing failed: {str(e)}")

    def global_graphiant_filter(self, config_payload, action="add", **kwargs):
        """
        Update the routing_policies section with a Graphiant filter (attachPoint GraphiantIn/GraphiantOut).

        Args:
            config_payload (dict): The configuration dictionary that holds routing policies.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional parameters used for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global Graphiant filter: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_global_graphiant_filter(action=action, **kwargs)
            if action == "add":
                config_payload["routing_policies"].update(result)
            else:  # delete
                config_payload["routing_policies"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global Graphiant filter %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global Graphiant filter processing failed: {str(e)}")

    def device_bgp_peering(self, config_payload, action="add", **kwargs):
        """
        Update the Device neighbors section of configuration payload.

        Args:
            config_payload (dict): Dictionary to be updated with BGP peering configuration.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional parameters used for rendering the BGP peering configuration.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["segments"])
        LOG.debug("Edge BGP peering: %s %s", action.upper(), kwargs.get("segments"))

        try:
            # Handle route policies global ID resolution (API expects integer; None renders as string "None")
            global_ids = {}
            if kwargs.get("route_policies"):
                for policy_name in kwargs.get("route_policies"):
                    rid = self.gsdk.get_global_routing_policy_id(policy_name)
                    if rid is None:
                        raise ConfigurationError(
                            f"Routing policy '{policy_name}' not found. "
                            "Configure global BGP filters first "
                            "(e.g. graphiant_global_config with sample_global_bgp_filters.yaml)."
                        )
                    global_ids[policy_name] = rid
                    LOG.debug("Global ID for %s: %s", policy_name, global_ids[policy_name])

            result = self.template.render_bgp_peering(action=action, global_ids=global_ids, **kwargs)
            config_payload.update(result)
        except Exception as e:
            LOG.error("Failed to process device BGP peering %s: %s", kwargs.get("segments"), str(e))
            raise ConfigurationError(f"Device BGP peering processing failed: {str(e)}")

    def device_interface(self, config_payload, action="add", **kwargs):
        """
        Update the device interfaces section of the configuration payload.

        Args:
            config_payload (dict): Dictionary to be updated with interface data.
            action (str, optional): Action to perform, either "add", "default_lan", or "delete".
            **kwargs: Additional parameters passed to the template renderer.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.info("Device interface: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_interface(action=action, **kwargs)
            if "interfaces" in result:
                config_payload["interfaces"].update(result["interfaces"])
            else:
                LOG.warning("No interfaces found in template result for %s", kwargs.get("name"))
        except Exception as e:
            LOG.error("Failed to process device interface %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Device interface processing failed: {str(e)}")

    def device_backbone_interface(self, config_payload, action="add", **kwargs):
        """
        Update the device interfaces section of a Graphiant Core (backbone) payload.

        Args:
            config_payload (dict): Dictionary to be updated with backbone interface data.
                Expected to already contain an "interfaces" key.
            action (str, optional): Action to perform, either "add", "default_lan", or "delete".
            **kwargs: Additional parameters passed to the template renderer
                (name, interface_type, lan, circuit, ipv4, ipv6, gateway, ospf, ...).

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.info("Device backbone interface: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_backbone_interface(action=action, **kwargs)
            if "interfaces" in result:
                config_payload.setdefault("interfaces", {})
                config_payload["interfaces"].update(result["interfaces"])
            else:
                LOG.warning("No interfaces found in backbone template result for %s", kwargs.get("name"))
        except Exception as e:
            LOG.error("Failed to process backbone interface %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Device backbone interface processing failed: {str(e)}")

    def lag_interfaces(self, config_payload, action="add", **kwargs):
        """
        Update the device interfaces section with LAG configuration.

        Args:
            config_payload (dict): Dictionary to be updated with LAG data.
            action (str, optional): Action to perform, either "add" or "delete".
            **kwargs: Additional parameters passed to the template renderer.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.info("LAG on interfaces: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_lag_interfaces(action=action, **kwargs)
            if "lagInterfaces" in result:
                config_payload["lagInterfaces"].update(result["lagInterfaces"])
            elif "interfaces" in result:
                config_payload["interfaces"].update(result["interfaces"])
            else:
                LOG.warning("No lagInterfaces found in LAG template result for %s", kwargs.get("name"))
        except Exception as e:
            LOG.error("Failed to process LAG on interfaces %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"LAG on interfaces processing failed: {str(e)}")

    def vrrp_interfaces(self, config_payload, action="add", **kwargs):
        """
        Update the device interfaces section with VRRP configuration.

        Args:
            config_payload (dict): Dictionary to be updated with VRRP data.
            action (str, optional): Action to perform, either "add" or "delete".
            **kwargs: Additional parameters passed to the template renderer.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.info("VRRP on interfaces: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_vrrp_interfaces(action=action, **kwargs)
            if "interfaces" in result:
                if "interfaces" not in config_payload:
                    config_payload["interfaces"] = {}
                config_payload["interfaces"].update(result["interfaces"])
            else:
                LOG.warning("No interfaces found in VRRP template result for %s", kwargs.get("name"))
        except Exception as e:
            LOG.error("Failed to process VRRP on interfaces %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"VRRP on interfaces processing failed: {str(e)}")

    def device_circuit(self, config_payload, action="add", **kwargs):
        """
        Update the device circuits section of the configuration payload.

        Args:
            config_payload (dict): Dictionary to be updated with circuit data.
            action (str, optional): Action to perform, either "add" or "delete".
            **kwargs: Additional parameters passed to the template renderer.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["circuit"])
        LOG.debug("Device circuit: %s %s", action.upper(), kwargs.get("circuit"))

        try:
            result = self.template.render_circuit(action=action, **kwargs)
            if "circuits" in result:
                config_payload["circuits"].update(result["circuits"])
            else:
                LOG.warning("No circuits found in template result for %s", kwargs.get("circuit"))
        except Exception as e:
            LOG.error("Failed to process device circuit %s: %s", kwargs.get("circuit"), str(e))
            raise ConfigurationError(f"Device circuit processing failed: {str(e)}")

    def global_snmp(self, config_payload, action="add", **kwargs):
        """
        Update the snmps section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global SNMP service: %s %s", action.upper(), kwargs.get("name"))

        try:
            result = self.template.render_snmp_service(action=action, **kwargs)
            if action == "add":
                config_payload["snmps"].update(result)
            else:  # delete
                config_payload["snmps"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global SNMP service %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global SNMP service processing failed: {str(e)}")

    def global_syslog(self, config_payload, action="add", **kwargs):
        """
        Update the syslogServers section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global syslog service: %s %s", action.upper(), kwargs.get("name"))

        try:
            # Convert lanSegment to vrfId if present
            if "target" in kwargs and "lanSegment" in kwargs["target"]:
                lan_segment = kwargs["target"]["lanSegment"]
                vrf_id = self.gsdk.get_lan_segment_id(lan_segment)
                kwargs["target"]["vrfId"] = vrf_id
                del kwargs["target"]["lanSegment"]
                LOG.debug("Converted lanSegment '%s' to vrfId %s", lan_segment, vrf_id)

            result = self.template.render_syslog_service(action=action, **kwargs)
            if action == "add":
                config_payload["syslog_servers"].update(result)
            else:  # delete
                config_payload["syslog_servers"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global syslog service %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global syslog service processing failed: {str(e)}")

    def global_ntp(self, config_payload, action="add", **kwargs):
        """
        Update the ntps section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: NTP config fields (e.g. domains, isGlobalSync).

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global NTP service: %s %s", action.upper(), kwargs.get("name"))

        try:
            name = kwargs.get("name")
            if action == "add":
                ntp_config = {
                    "config": {
                        "name": name,
                        "domains": list(kwargs.get("domains") or []),
                    }
                }
                # Optional fields supported by SDK model; only include if explicitly provided.
                if "globalId" in kwargs and kwargs.get("globalId") is not None:
                    ntp_config["config"]["globalId"] = kwargs.get("globalId")
                if "isGlobalSync" in kwargs and kwargs.get("isGlobalSync") is not None:
                    ntp_config["config"]["isGlobalSync"] = bool(kwargs.get("isGlobalSync"))
                config_payload["ntps"][name] = ntp_config
            else:  # delete
                config_payload["ntps"][name] = {}
        except Exception as e:
            LOG.error("Failed to process global NTP service %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global NTP service processing failed: {str(e)}")

    def global_ipfix(self, config_payload, action="add", **kwargs):
        """
        Update the ipfixExporters section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global IPFIX service: %s %s", action.upper(), kwargs.get("name"))

        try:
            # Convert lanSegment to vrfId if present in exporter
            if "exporter" in kwargs and "lanSegment" in kwargs["exporter"]:
                lan_segment = kwargs["exporter"]["lanSegment"]
                vrf_id = self.gsdk.get_lan_segment_id(lan_segment)
                kwargs["exporter"]["vrfId"] = vrf_id
                del kwargs["exporter"]["lanSegment"]
                LOG.debug("Converted lanSegment '%s' to vrfId %s", lan_segment, vrf_id)

            result = self.template.render_ipfix_service(action=action, **kwargs)
            if action == "add":
                config_payload["ipfix_exporters"].update(result)
            else:  # delete
                config_payload["ipfix_exporters"][kwargs.get("name")] = {}
        except Exception as e:
            LOG.error("Failed to process global IPFIX service %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global IPFIX service processing failed: {str(e)}")

    def global_vpn_profile(self, config_payload, action="add", **kwargs):
        """
        Update the vpnProfiles section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global VPN profile service: %s %s", action.upper(), kwargs.get("name"))

        try:
            # Pass the VPN config as a list to match the template expectation
            vpn_profiles_list = [kwargs]
            result = self.template.render_vpn_profile(vpn_profiles=vpn_profiles_list)

            if action == "add":
                # Extract the actual VPN profile data from the template result
                if "vpn_profiles" in result:
                    config_payload["vpn_profiles"].update(result["vpn_profiles"])
                else:
                    LOG.warning("No vpn_profiles found in template result for %s", kwargs.get("name"))
            else:  # delete
                name = kwargs.get("name")
                if name:
                    config_payload["vpn_profiles"][name] = {}
        except Exception as e:
            LOG.error("Failed to process global VPN profile service %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global VPN profile service processing failed: {str(e)}")

    def global_site_list(self, config_payload, action="add", **kwargs):
        """
        Update the site_lists section of configuration payload.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Raises:
            ConfigurationError: If required parameters are missing.
        """
        self._validate_required_params(kwargs, ["name"])
        LOG.debug("Global site list: %s %s", action.upper(), kwargs.get("name"))

        try:
            if action == "add":
                # Use template for complex payload generation
                result = self.template.render_site_list(action=action, **kwargs)
                config_payload["site_lists"].update(result)
            else:  # delete
                # Simple delete logic in code
                name = kwargs.get("name")
                if name:
                    config_payload["site_lists"][name] = {}
        except Exception as e:
            LOG.error("Failed to process global site list %s: %s", kwargs.get("name"), str(e))
            raise ConfigurationError(f"Global site list processing failed: {str(e)}")
