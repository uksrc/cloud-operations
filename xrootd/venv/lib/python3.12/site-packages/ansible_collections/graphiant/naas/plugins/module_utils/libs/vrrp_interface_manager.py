"""
VRRP on Interfaces Manager for Graphiant Playbooks.

This module handles VRRP interface configuration management for Graphiant Playbooks.

VRRP configuration is applied to both main interfaces and subinterfaces (VLANs).

Idempotency Support:
    - deconfigure: Checks if VRRP is already disabled before pushing config.
      Skips interfaces where VRRP is already disabled (enabled=false).
"""

from typing import Any, Dict

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class VRRPInterfaceManager(BaseManager):
    """
    Manages VRRP on interfaces configurations.

    Handles the configuration and deconfiguration of VRRP interfaces,
    including both main interfaces and VLAN subinterfaces.
    """

    @staticmethod
    def _get_existing_vrrp_state(gcs_device_info, interface_name, vlan=None):
        """
        Get existing VRRP state for an interface from device info.

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()
            interface_name: Name of the interface (e.g., 'GigabitEthernet7/0/0')
            vlan: Optional VLAN ID for subinterface VRRP

        Returns:
            dict: Dictionary with VRRP state for ipv4 and ipv6:
                  {'ipv4': {'enabled': bool, 'virtualRouterId': int},
                   'ipv6': {'enabled': bool, 'virtualRouterId': int}}
                  Returns None if interface not found or no VRRP configured.
        """
        vrrp_state = {"ipv4": None, "ipv6": None}

        if not hasattr(gcs_device_info, "device"):
            LOG.debug("_get_existing_vrrp_state: No 'device' attribute in gcs_device_info")
            return vrrp_state

        device = gcs_device_info.device
        if not hasattr(device, "interfaces") or not device.interfaces:
            LOG.debug("_get_existing_vrrp_state: No interfaces found on device")
            return vrrp_state

        # Find the interface
        target_interface = None
        for interface in device.interfaces:
            if getattr(interface, "name", None) == interface_name:
                target_interface = interface
                break

        if not target_interface:
            LOG.debug("_get_existing_vrrp_state: Interface '%s' not found", interface_name)
            return vrrp_state

        # Get interface object - either main interface or subinterface
        intf_obj = None
        if vlan:
            # Look for subinterface - check both integer and string vlan
            vlan_int = int(vlan) if vlan else None
            if hasattr(target_interface, "subinterfaces") and target_interface.subinterfaces:
                LOG.debug(
                    "_get_existing_vrrp_state: Found %d subinterfaces on %s",
                    len(target_interface.subinterfaces),
                    interface_name,
                )
                for subintf in target_interface.subinterfaces:
                    subintf_vlan = getattr(subintf, "vlan", None)
                    LOG.debug(
                        "_get_existing_vrrp_state: Checking subinterface vlan=%s (looking for %s)",
                        subintf_vlan,
                        vlan_int,
                    )
                    if subintf_vlan == vlan_int:
                        intf_obj = subintf
                        LOG.debug("_get_existing_vrrp_state: Found matching subinterface vlan=%s", vlan_int)
                        break
            else:
                LOG.debug("_get_existing_vrrp_state: No subinterfaces on %s", interface_name)
        else:
            # Main interface
            intf_obj = target_interface

        if not intf_obj:
            LOG.debug(
                "_get_existing_vrrp_state: Interface object not found for %s%s",
                interface_name,
                f".{vlan}" if vlan else "",
            )
            return vrrp_state

        # Check IPv4 VRRP - API returns 'vrrp_group' not 'vrrp'
        ipv4_obj = getattr(intf_obj, "ipv4", None)
        if ipv4_obj:
            # The API returns VRRP data directly as 'vrrp_group' (not nested under 'vrrp')
            vrrp_group = getattr(ipv4_obj, "vrrp_group", None)
            LOG.debug(
                "_get_existing_vrrp_state: %s%s - IPv4 vrrp_group exists: %s",
                interface_name,
                f".{vlan}" if vlan else "",
                vrrp_group is not None,
            )
            if vrrp_group:
                enabled_value = getattr(vrrp_group, "enabled", None)
                vrrp_state["ipv4"] = {
                    "enabled": enabled_value,
                    "virtualRouterId": getattr(vrrp_group, "virtual_router_id", None),
                }
                LOG.info(
                    "_get_existing_vrrp_state: %s%s - IPv4 VRRP state: enabled=%s",
                    interface_name,
                    f".{vlan}" if vlan else "",
                    vrrp_state["ipv4"]["enabled"],
                )

        # Check IPv6 VRRP - API returns 'vrrp_group' not 'vrrp'
        ipv6_obj = getattr(intf_obj, "ipv6", None)
        if ipv6_obj:
            vrrp_group = getattr(ipv6_obj, "vrrp_group", None)
            LOG.debug(
                "_get_existing_vrrp_state: %s%s - IPv6 vrrp_group exists: %s",
                interface_name,
                f".{vlan}" if vlan else "",
                vrrp_group is not None,
            )
            if vrrp_group:
                enabled_value = getattr(vrrp_group, "enabled", None)
                vrrp_state["ipv6"] = {
                    "enabled": enabled_value,
                    "virtualRouterId": getattr(vrrp_group, "virtual_router_id", None),
                }
                LOG.info(
                    "_get_existing_vrrp_state: %s%s - IPv6 VRRP state: enabled=%s",
                    interface_name,
                    f".{vlan}" if vlan else "",
                    vrrp_state["ipv6"]["enabled"],
                )

        return vrrp_state

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
        """
        return self.configure_vrrp_interfaces(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces
        """
        return self.deconfigure_vrrp_interfaces(config_yaml_file)

    def enable_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Enable existing VRRP interfaces for multiple devices concurrently (idempotent).

        This operation only enables VRRP that is already configured. It does not create
        new VRRP configurations. If VRRP is already enabled, the operation is skipped.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP interface references

        Returns:
            dict: Result with 'changed' status, enabled and skipped devices/interfaces

        Raises:
            ConfigurationError: If VRRP configuration doesn't exist or processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "enabled_devices": [],
            "enabled_interfaces": [],
            "skipped_interfaces": [],
        }

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[enable] Processing device: %s (ID: %s)", device_name, device_id)

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Process VRRP enable for this device
                    vrrp_to_enable = 0
                    vrrp_skipped = 0

                    for config in configs.get("interfaces", []):
                        interface_name = config.get("name")
                        vlan = config.get("vlan")
                        vrrp_ipv4 = config.get("vrrp_ipv4")
                        vrrp_ipv6 = config.get("vrrp_ipv6")

                        # Get existing VRRP state
                        existing_vrrp = self._get_existing_vrrp_state(gcs_device_info, interface_name, vlan)

                        # Check if any VRRP needs to be enabled
                        needs_enable = False
                        has_vrrp_config = False

                        # Check IPv4 VRRP
                        if vrrp_ipv4:
                            if existing_vrrp["ipv4"] is None:
                                raise ConfigurationError(
                                    f"VRRP IPv4 configuration does not exist on {interface_name}"
                                    f"{f'.{vlan}' if vlan else ''} for device '{device_name}'. "
                                    "Please configure VRRP first before enabling it."
                                )
                            has_vrrp_config = True
                            if existing_vrrp["ipv4"].get("enabled") is not True:
                                needs_enable = True
                                LOG.info(
                                    " ✓ IPv4 VRRP is disabled on %s%s, will enable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ IPv4 VRRP already enabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        # Check IPv6 VRRP
                        if vrrp_ipv6:
                            if existing_vrrp["ipv6"] is None:
                                raise ConfigurationError(
                                    f"VRRP IPv6 configuration does not exist on {interface_name}"
                                    f"{f'.{vlan}' if vlan else ''} for device '{device_name}'. "
                                    "Please configure VRRP first before enabling it."
                                )
                            has_vrrp_config = True
                            if existing_vrrp["ipv6"].get("enabled") is not True:
                                needs_enable = True
                                LOG.info(
                                    " ✓ IPv6 VRRP is disabled on %s%s, will enable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ IPv6 VRRP already enabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        if not has_vrrp_config:
                            LOG.warning(
                                " ✗ No VRRP configuration specified for %s%s, skipping",
                                interface_name,
                                f".{vlan}" if vlan else "",
                            )
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "No VRRP config specified",
                                }
                            )
                            continue

                        if needs_enable:
                            # Initialize device config if not already
                            if device_id not in output_config:
                                output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                            # Build config dict for template (no virtualRouterId needed for enable)
                            enable_config = {"name": interface_name}
                            if vlan:
                                enable_config["vlan"] = vlan

                            # Add vrrp_ipv4/vrrp_ipv6 keys (empty dict is fine, template only needs the key)
                            if vrrp_ipv4 and existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is not True:
                                enable_config["vrrp_ipv4"] = {}

                            if vrrp_ipv6 and existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is not True:
                                enable_config["vrrp_ipv6"] = {}

                            # Use template to generate payload (consistent with deconfigure)
                            self.config_utils.vrrp_interfaces(
                                output_config[device_id]["edge"], action="enable", **enable_config
                            )

                            vrrp_to_enable += 1
                            result["enabled_interfaces"].append(
                                {"device": device_name, "interface": interface_name, "vlan": vlan}
                            )
                        else:
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "VRRP already enabled",
                                }
                            )

                    LOG.info(
                        "Device %s summary: %d VRRP interface(s) to enable, %d skipped (already enabled)",
                        device_name,
                        vrrp_to_enable,
                        vrrp_skipped,
                    )

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except ConfigurationError:
                    raise
                except Exception as e:
                    LOG.error("Error enabling VRRP on device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Enable VRRP failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["enabled_devices"] = list(output_config.keys())
                LOG.info(
                    "VRRP enable completed: %d device(s) updated, %d interface(s) enabled, "
                    "%d interface(s) skipped (already enabled) (changed: %s)",
                    len(output_config),
                    len(result["enabled_interfaces"]),
                    len(result["skipped_interfaces"]),
                    result["changed"],
                )
            else:
                LOG.info("No VRRP changes needed - all interfaces already enabled (changed: %s)", result["changed"])

            return result

        except Exception as e:
            LOG.error("Error in VRRP interface enable: %s", str(e))
            raise ConfigurationError(f"VRRP interface enable failed: {str(e)}")

    def configure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Configure VRRP interfaces for multiple devices concurrently.
        This method combines all VRRP configurations in a single API call per device.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )
                    output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                    # Collect interface names referenced in this device's VRRP configurations
                    referenced_interfaces = set()
                    for vrrp_config in configs.get("interfaces", []):
                        # Check main interface for interface reference
                        if vrrp_config.get("name"):
                            referenced_interfaces.add(vrrp_config["name"])
                        # Check subinterfaces for interface references
                        if vrrp_config.get("vlan"):
                            referenced_interfaces.add(vrrp_config["vlan"])

                    LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced interfaces: %s", list(referenced_interfaces))

                    # Process VRRP for this device
                    vrrp_configured = 0
                    for config in configs.get("interfaces", []):
                        # Check if this interface has any VRRP configuration
                        if config.get("vrrp_ipv4") or config.get("vrrp_ipv6"):
                            LOG.info(" ✓ Found VRRP configuration for interface: %s", config.get("name"))
                            self.config_utils.vrrp_interfaces(output_config[device_id]["edge"], action="add", **config)
                            vrrp_configured += 1
                            LOG.info(" ✓ To configure VRRP for interface: %s", config.get("name"))
                        else:
                            LOG.info(" ✗ Skipping interface '%s' - no VRRP configuration", config.get("name"))

                    LOG.info("Device %s summary: %s VRRP interfaces to be configured", device_name, vrrp_configured)
                    LOG.info("Final config for %s: %s", device_name, output_config[device_id]["edge"])

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["configured_devices"] = list(output_config.keys())
                LOG.info(
                    "VRRP configuration completed: %d device(s) configured (changed: %s)",
                    len(output_config),
                    result["changed"],
                )
            else:
                LOG.info("No VRRP configurations to apply (changed: %s)", result["changed"])

            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in VRRP interface configuration: %s", str(e))
            raise ConfigurationError(f"VRRP interface configuration failed: {str(e)}")

    def deconfigure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Deconfigure VRRP interfaces for multiple devices concurrently (idempotent).

        Checks if VRRP is already disabled before pushing configuration.
        Skips interfaces where VRRP is already disabled.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "deconfigured_interfaces": [],
            "skipped_interfaces": [],
        }

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Process VRRP removal for this device
                    vrrp_to_deconfigure = 0
                    vrrp_skipped = 0

                    for config in configs.get("interfaces", []):
                        interface_name = config.get("name")
                        vlan = config.get("vlan")
                        vrrp_ipv4 = config.get("vrrp_ipv4")
                        vrrp_ipv6 = config.get("vrrp_ipv6")

                        # Get existing VRRP state for idempotency check
                        existing_vrrp = self._get_existing_vrrp_state(gcs_device_info, interface_name, vlan)

                        # Check if any VRRP needs to be disabled
                        needs_deconfigure = False

                        # Check IPv4 VRRP
                        if vrrp_ipv4:
                            if existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is True:
                                needs_deconfigure = True
                                LOG.info(
                                    " ✓ IPv4 VRRP is enabled on %s%s, will disable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            elif existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is False:
                                LOG.info(
                                    " ✗ IPv4 VRRP already disabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ No IPv4 VRRP configured on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        # Check IPv6 VRRP
                        if vrrp_ipv6:
                            if existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is True:
                                needs_deconfigure = True
                                LOG.info(
                                    " ✓ IPv6 VRRP is enabled on %s%s, will disable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            elif existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is False:
                                LOG.info(
                                    " ✗ IPv6 VRRP already disabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ No IPv6 VRRP configured on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        if needs_deconfigure:
                            # Initialize device config if not already
                            if device_id not in output_config:
                                output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                            self.config_utils.vrrp_interfaces(
                                output_config[device_id]["edge"], action="delete", **config
                            )
                            vrrp_to_deconfigure += 1
                            result["deconfigured_interfaces"].append(
                                {"device": device_name, "interface": interface_name, "vlan": vlan}
                            )
                        else:
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "VRRP already disabled or not configured",
                                }
                            )

                    LOG.info(
                        "Device %s summary: %d VRRP interface(s) to deconfigure, %d skipped (already disabled)",
                        device_name,
                        vrrp_to_deconfigure,
                        vrrp_skipped,
                    )

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info(
                    "VRRP deconfiguration completed: %d device(s) updated, %d interface(s) deconfigured, "
                    "%d interface(s) skipped (changed: %s)",
                    len(output_config),
                    len(result["deconfigured_interfaces"]),
                    len(result["skipped_interfaces"]),
                    result["changed"],
                )

                # Explicit lists for consistency with global_config deconfigure logging
                def _entry_name(ent):
                    suffix = (".%s" % ent["vlan"]) if ent.get("vlan") else ""
                    return "%s:%s%s" % (ent.get("device", ""), ent.get("interface", ""), suffix)

                deconfigured_names = [_entry_name(e) for e in result["deconfigured_interfaces"]]
                skipped_names = [_entry_name(e) for e in result["skipped_interfaces"]]
                LOG.info(
                    "Deconfigure completed: deconfigured_interfaces=%s, skipped_interfaces=%s",
                    deconfigured_names,
                    skipped_names,
                )
            else:
                LOG.info(
                    "No VRRP changes needed - all interfaces already disabled or not configured (changed: %s)",
                    result["changed"],
                )

            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in VRRP interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"VRRP interface deconfiguration failed: {str(e)}")
