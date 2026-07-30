"""
Interface Manager for Graphiant Playbooks.

This module handles interface and circuit configuration management,
including both regular interfaces and sub-interfaces.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class InterfaceManager(BaseManager):
    """
    Manages interface and circuit configurations.

    Handles the configuration and deconfiguration of network interfaces,
    including both regular interfaces and VLAN sub-interfaces.

    Notes:
        - Configure workflows push configuration via PUT and may not be fully idempotent.
        - Deconfigure workflows are designed to be idempotent by checking current device state
          (via `gsdk.get_device_info`) before building delete payloads.
        - For WAN circuits, the backend can treat "detaching a circuit from an interface" as a
          circuit removal operation. If that circuit still has static routes, the request may
          fail with: `error removing circuit "<name>". Remove static routes first.`
          Use `deconfigure_wan_circuits_interfaces()` or `deconfigure_interfaces()` to ensure
          static routes are removed before WAN interface reset/detach.
    """

    @staticmethod
    def _get_subinterfaces(interface_config):
        """Get subinterfaces from config, supporting both 'subinterfaces' and 'sub_interfaces' keys."""
        return interface_config.get("subinterfaces") or interface_config.get("sub_interfaces") or []

    @staticmethod
    def _check_interface_exists(gcs_device_info, interface_name, vlan=None):
        """
        Check if an interface or subinterface exists on the device.

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()
            interface_name: Name of the interface (e.g., 'GigabitEthernet7/0/0')
            vlan: Optional VLAN ID for subinterface

        Returns:
            bool: True if interface/subinterface exists, False otherwise
        """
        if not hasattr(gcs_device_info, "device"):
            return False

        device = gcs_device_info.device
        if not hasattr(device, "interfaces") or not device.interfaces:
            return False

        # Find the interface
        target_interface = None
        for interface in device.interfaces:
            if getattr(interface, "name", None) == interface_name:
                target_interface = interface
                break

        if not target_interface:
            return False

        # If checking for subinterface
        if vlan:
            vlan_int = int(vlan) if vlan else None
            if hasattr(target_interface, "subinterfaces") and target_interface.subinterfaces:
                for subintf in target_interface.subinterfaces:
                    subintf_vlan = getattr(subintf, "vlan", None)
                    if subintf_vlan == vlan_int:
                        return True
            return False

        # Main interface exists
        return True

    @staticmethod
    def _get_interface_obj(gcs_device_info, interface_name):
        """Return the interface object from device info, if present."""
        if not hasattr(gcs_device_info, "device"):
            return None
        device = gcs_device_info.device
        if not hasattr(device, "interfaces") or not device.interfaces:
            return None
        for interface in device.interfaces:
            if getattr(interface, "name", None) == interface_name:
                return interface
        return None

    @classmethod
    def _get_interface_lan(cls, gcs_device_info, interface_name):
        """
        Best-effort extraction of the interface LAN segment identifier/name from device info.
        Returns None if not available.
        """
        interface = cls._get_interface_obj(gcs_device_info, interface_name)
        if not interface:
            return None

        # Common attribute names seen across SDK models / versions
        for attr in ("lan", "lanSegment", "lan_segment"):
            val = getattr(interface, attr, None)
            if val is None:
                continue
            if isinstance(val, str):
                return val
            # SDK objects sometimes wrap values; prefer "name" if present
            if hasattr(val, "name"):
                return getattr(val, "name")
            return str(val)
        return None

    @classmethod
    def _get_subinterface_lan(cls, gcs_device_info, interface_name, vlan):
        """
        Best-effort extraction of a subinterface's LAN segment from device info.
        Returns None if not available.
        """
        interface = cls._get_interface_obj(gcs_device_info, interface_name)
        if not interface or not hasattr(interface, "subinterfaces") or not interface.subinterfaces:
            return None
        vlan_int = int(vlan) if vlan is not None else None
        for subintf in interface.subinterfaces:
            if getattr(subintf, "vlan", None) == vlan_int:
                for attr in ("lan", "lanSegment", "lan_segment"):
                    val = getattr(subintf, attr, None)
                    if val is None:
                        continue
                    if isinstance(val, str):
                        return val
                    if hasattr(val, "name"):
                        return getattr(val, "name")
                    return str(val)
                return None
        return None

    @classmethod
    def _get_interface_circuit(cls, gcs_device_info, interface_name):
        """
        Best-effort extraction of the interface circuit identifier/name from device info.
        Returns None if not available / not set.
        """
        interface = cls._get_interface_obj(gcs_device_info, interface_name)
        if not interface:
            return None

        # Common attribute names seen across SDK models / versions
        for attr in ("circuit", "wanCircuit", "wan_circuit"):
            val = getattr(interface, attr, None)
            if val is None:
                continue
            if isinstance(val, str):
                return val
            if hasattr(val, "name"):
                return getattr(val, "name")
            return str(val)
        return None

    @staticmethod
    def _get_circuits_list(gcs_device_info):
        """Return circuits list from SDK device info (best-effort)."""
        if not hasattr(gcs_device_info, "device"):
            return []
        return getattr(gcs_device_info.device, "circuits", None) or []

    @classmethod
    def _get_circuit_obj(cls, gcs_device_info, circuit_name):
        """Return the circuit object from device info, if present."""
        for circuit in cls._get_circuits_list(gcs_device_info):
            if getattr(circuit, "name", None) == circuit_name:
                return circuit
        return None

    @classmethod
    def _get_circuit_static_route_prefixes(cls, gcs_device_info, circuit_name):
        """
        Return a set of static route prefixes currently present on a circuit.

        SDK models typically represent this as:
        - device.circuits[] (ManaV2Circuit)
        - circuit.static_routes[] (List[ManaV2StaticRoute])
        - static_route.prefix (str)
        """
        circuit = cls._get_circuit_obj(gcs_device_info, circuit_name)
        if not circuit:
            return set()

        static_routes = getattr(circuit, "static_routes", None)
        if static_routes is None:
            static_routes = getattr(circuit, "staticRoutes", None)  # fallback for older SDK naming
        if not static_routes:
            return set()

        # SDK model: List[ManaV2StaticRoute] where each route has .prefix
        if isinstance(static_routes, (list, tuple)):
            return {r.prefix for r in static_routes if getattr(r, "prefix", None)}

        # Defensive: some SDKs/serializers can expose this as dict keyed by prefix
        if isinstance(static_routes, dict):
            return {p for p, v in static_routes.items() if v not in (None, {})}

        if hasattr(static_routes, "to_dict"):
            try:
                sr = static_routes.to_dict()
                if isinstance(sr, dict):
                    return {p for p, v in sr.items() if v not in (None, {})}
            except Exception:  # pylint: disable=broad-except
                return set()

        return set()

    def configure(
        self,
        config_yaml_file=None,
        circuit_config_file=None,
        *,
        interface_config_file=None,
    ) -> dict:
        """
        Configure interfaces and circuits for multiple devices concurrently.
        This method combines all interface and circuit configurations in a single API call per device.

        Args:
            config_yaml_file: Path to the YAML file containing interface configurations (preferred; matches BaseManager)
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            interface_config_file: Backward-compatible alias for ``config_yaml_file``
                (keyword-only). Use one or the other.

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        yaml_path = config_yaml_file if config_yaml_file is not None else interface_config_file
        if yaml_path is None:
            raise TypeError(
                "configure() requires config_yaml_file (positional or keyword) or interface_config_file= (alias)"
            )
        if (
            config_yaml_file is not None
            and interface_config_file is not None
            and config_yaml_file != interface_config_file
        ):
            raise TypeError(
                "configure(): pass either config_yaml_file or interface_config_file=, not two different paths"
            )

        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            # Load interface configurations
            interface_config_data = self.render_config_file(yaml_path)
            output_config = {}

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            if "interfaces" not in interface_config_data:
                LOG.warning("No interfaces configuration found in %s", yaml_path)
                return result

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            for device_info in interface_config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": [], "circuits": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

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
                    output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}, "circuits": {}}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device
                    circuits_configured = 0
                    for circuit_config in configs.get("circuits", []):
                        if circuit_config.get("circuit") in referenced_circuits:
                            self.config_utils.device_circuit(
                                output_config[device_id]["edge"], action="add", **circuit_config
                            )
                            circuits_configured += 1
                            LOG.info(
                                " ✓ To configure circuit '%s' for device: %s",
                                circuit_config.get("circuit"),
                                device_name,
                            )
                        else:
                            LOG.info(
                                " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                circuit_config.get("circuit"),
                            )

                    # Process all interfaces for this device (both LAN and WAN)
                    interfaces_configured = 0
                    for interface_config in configs.get("interfaces", []):
                        # Check if this interface has any configuration (LAN or WAN)
                        has_lan_main = interface_config.get("lan") is not None
                        has_wan_main = interface_config.get("circuit") is not None
                        lan_subinterfaces = []
                        wan_subinterfaces = []

                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("lan"):
                                lan_subinterfaces.append(sub_interface)
                            if sub_interface.get("circuit"):
                                wan_subinterfaces.append(sub_interface)

                        # Process this interface if it has any configuration
                        if has_lan_main or has_wan_main or lan_subinterfaces or wan_subinterfaces:
                            # Combine all subinterfaces
                            all_subinterfaces = lan_subinterfaces + wan_subinterfaces

                            if all_subinterfaces:
                                # Interface has subinterfaces
                                combined_config = interface_config.copy()
                                combined_config["sub_interfaces"] = all_subinterfaces
                                self.config_utils.device_interface(
                                    output_config[device_id]["edge"], action="add", **combined_config
                                )
                                interfaces_configured += 1 + len(all_subinterfaces)
                                LOG.info(
                                    " ✓ To configure interface '%s' with %s subinterfaces for device: %s",
                                    interface_config.get("name"),
                                    len(all_subinterfaces),
                                    device_name,
                                )
                            else:
                                # Interface has no subinterfaces
                                self.config_utils.device_interface(
                                    output_config[device_id]["edge"], action="add", **interface_config
                                )
                                interfaces_configured += 1
                                LOG.info(
                                    " ✓ To configure interface '%s' for device: %s",
                                    interface_config.get("name"),
                                    device_name,
                                )
                        else:
                            LOG.info(
                                " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                            )

                    LOG.info(
                        "Device %s summary: %s circuits, %s interfaces to be configured",
                        device_name,
                        circuits_configured,
                        interfaces_configured,
                    )
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
                LOG.info("Successfully configured interfaces and circuits for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in interface and circuit configuration: %s", str(e))
            raise ConfigurationError(f"Interface and circuit configuration failed: {str(e)}")

    def deconfigure(
        self,
        config_yaml_file=None,
        circuit_config_file=None,
        circuits_only: bool = False,
        *,
        interface_config_file=None,
    ) -> dict:
        """
        Deconfigure interfaces and (optionally) circuit static routes for multiple devices concurrently (idempotent).

        This is the low-level deconfigure implementation that builds a single per-device payload.
        It checks current device state (interfaces, subinterfaces, LAN/circuit attachment) before
        building a delete payload.

        Important WAN note:
          - When resetting a WAN interface, the payload detaches the circuit (sets `circuit: null`).
            The backend may treat that as a circuit removal and fail if static routes still exist.
          - This method does NOT stage circuit-static-route deletion ahead of interface reset when
            `circuits_only=False`. For WAN-safe staged deconfiguration, use:
            `deconfigure_wan_circuits_interfaces(..., circuits_only=False)` or
            `deconfigure_interfaces(..., circuits_only=False)`.

        Args:
            config_yaml_file: Path to the YAML file containing interface configurations (preferred; matches BaseManager)
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only remove circuit static routes (skip interface deconfiguration)
            interface_config_file: Backward-compatible alias for ``config_yaml_file``
                (keyword-only). Use one or the other.

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        yaml_path = config_yaml_file if config_yaml_file is not None else interface_config_file
        if yaml_path is None:
            raise TypeError(
                "deconfigure() requires config_yaml_file (positional or keyword) or interface_config_file= (alias)"
            )
        if (
            config_yaml_file is not None
            and interface_config_file is not None
            and config_yaml_file != interface_config_file
        ):
            raise TypeError(
                "deconfigure(): pass either config_yaml_file or interface_config_file=, not two different paths"
            )

        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "deconfigured_interfaces": [],
            "skipped_interfaces": [],
        }

        try:
            # Load interface configurations
            interface_config_data = self.render_config_file(yaml_path)
            output_config = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            if "interfaces" not in interface_config_data:
                LOG.warning("No interfaces configuration found in %s", yaml_path)
                return result

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            for device_info in interface_config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": [], "circuits": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

            LOG.info(
                "Attempting to deconfigure interfaces for devices: %s (circuits_only=%s)",
                list(device_configs.keys()),
                circuits_only,
            )

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

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Only include sections we actually intend to change.
                    # Avoid sending empty {"circuits": {}} which some backends interpret as "delete all circuits".
                    device_config: Dict[str, Any] = {"interfaces": {}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device (explicit deconfiguration for circuits with staticRoutes)
                    circuits_deconfigured = 0
                    if circuits_only:
                        for circuit_config in configs.get("circuits", []):
                            if circuit_config.get("circuit") in referenced_circuits:
                                circuit_name = circuit_config.get("circuit")
                                # Idempotency: only push deletions for staticRoutes that actually exist
                                existing_prefixes = self._get_circuit_static_route_prefixes(
                                    gcs_device_info, circuit_name
                                )
                                if not existing_prefixes:
                                    LOG.info(
                                        " ✓ Circuit '%s' has no staticRoutes on %s, skipping", circuit_name, device_name
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": circuit_name,
                                            "vlan": None,
                                            "reason": "Circuit has no staticRoutes",
                                        }
                                    )
                                    continue

                                # If config provides specific static_routes, delete only those that exist;
                                # otherwise delete all existing staticRoutes on the circuit.
                                requested_routes = circuit_config.get("static_routes")
                                if requested_routes:
                                    requested_prefixes = set(requested_routes.keys())
                                    prefixes_to_delete = sorted(existing_prefixes.intersection(requested_prefixes))
                                else:
                                    prefixes_to_delete = sorted(existing_prefixes)

                                if not prefixes_to_delete:
                                    LOG.info(
                                        " ✓ Circuit '%s' staticRoutes already removed on %s, skipping",
                                        circuit_name,
                                        device_name,
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": circuit_name,
                                            "vlan": None,
                                            "reason": "StaticRoutes already removed",
                                        }
                                    )
                                    continue

                                delete_config = circuit_config.copy()
                                # Ensure we always generate explicit route deletions (route:null)
                                # instead of empty staticRoutes:{}
                                delete_config["static_routes"] = {pfx: {} for pfx in prefixes_to_delete}

                                device_config.setdefault("circuits", {})
                                self.config_utils.device_circuit(device_config, action="delete", **delete_config)
                                circuits_deconfigured += 1
                                LOG.info(
                                    " ✓ To deconfigure %s staticRoutes on circuit '%s' for device: %s",
                                    len(prefixes_to_delete),
                                    circuit_name,
                                    device_name,
                                )
                            else:
                                LOG.info(
                                    " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                    circuit_config.get("circuit"),
                                )

                    # Process all interfaces for this device (both LAN and WAN) - skip if circuits_only=True
                    interfaces_deconfigured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # Check if this interface has any configuration (LAN or WAN)
                            has_lan_main = interface_config.get("lan") is not None
                            has_wan_main = interface_config.get("circuit") is not None
                            lan_subinterfaces = []
                            wan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)

                            # Process this interface if it has any configuration
                            if has_lan_main or has_wan_main or lan_subinterfaces or wan_subinterfaces:
                                interface_name = interface_config.get("name")
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                current_circuit = (
                                    self._get_interface_circuit(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )

                                # For ethernet interfaces, "deconfigure main" means:
                                # - set parent LAN to default LAN
                                # - clear circuit
                                # We should only do that if the parent isn't already in that state.
                                parent_requested = bool(has_lan_main or has_wan_main)
                                main_needs_reset = (
                                    main_interface_exists
                                    and parent_requested
                                    and ((current_lan != default_lan) or (current_circuit is not None))
                                )

                                # Check if main interface exists
                                if parent_requested:
                                    if not main_interface_exists:
                                        LOG.info(
                                            " ✗ Interface '%s' does not exist on %s, skipping",
                                            interface_name,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": None,
                                                "reason": "Interface does not exist",
                                            }
                                        )
                                    elif main_needs_reset:
                                        LOG.info(
                                            " ✓ Interface '%s' exists on %s (lan=%s circuit=%s), will reset to %s",
                                            interface_name,
                                            device_name,
                                            current_lan,
                                            current_circuit,
                                            default_lan,
                                        )
                                    else:
                                        LOG.info(
                                            " ✓ Interface '%s' already at default state on %s "
                                            "(lan=%s circuit=%s), skipping parent reset",
                                            interface_name,
                                            device_name,
                                            current_lan,
                                            current_circuit,
                                        )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in lan_subinterfaces + wan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        needs_deconfigure = True
                                        LOG.info(
                                            " ✓ Subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ Subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if needs_deconfigure:
                                    if existing_subinterfaces:
                                        # Interface has subinterfaces
                                        combined_config = interface_config.copy()
                                        # Remove any existing subinterface keys to avoid including
                                        # non-existent subinterfaces
                                        combined_config.pop("sub_interfaces", None)
                                        combined_config.pop("subinterfaces", None)
                                        combined_config["sub_interfaces"] = existing_subinterfaces

                                        # If the parent is already at default state, don't include
                                        # lan/circuit in payload.
                                        # This ensures we only delete subinterfaces (as per config)
                                        # without resetting parent again.
                                        if parent_requested and not main_needs_reset:
                                            combined_config.pop("lan", None)
                                            combined_config.pop("circuit", None)

                                        self.config_utils.device_interface(
                                            device_config, action="delete", default_lan=default_lan, **combined_config
                                        )
                                        interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                            existing_subinterfaces
                                        )
                                        LOG.info(
                                            " ✓ To deconfigure interface '%s' with %s subinterfaces for device: %s",
                                            interface_name,
                                            len(existing_subinterfaces),
                                            device_name,
                                        )
                                        if main_needs_reset:
                                            result["deconfigured_interfaces"].append(
                                                {"device": device_name, "interface": interface_name, "vlan": None}
                                            )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )
                                    elif main_needs_reset:
                                        # Interface has no subinterfaces (or all subinterfaces were skipped)
                                        # Remove any subinterface keys to avoid including non-existent subinterfaces
                                        clean_config = interface_config.copy()
                                        clean_config.pop("sub_interfaces", None)
                                        clean_config.pop("subinterfaces", None)
                                        self.config_utils.device_interface(
                                            device_config, action="delete", default_lan=default_lan, **clean_config
                                        )
                                        interfaces_deconfigured += 1
                                        LOG.info(
                                            " ✓ To deconfigure interface '%s' for device: %s",
                                            interface_name,
                                            device_name,
                                        )
                                        result["deconfigured_interfaces"].append(
                                            {"device": device_name, "interface": interface_name, "vlan": None}
                                        )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )
                    else:
                        LOG.info(" ✗ Skipping interface '%s' - no configuration found", interface_config.get("name"))

                    # Only add to output_config if there's something to deconfigure
                    if device_config.get("interfaces") or device_config.get("circuits"):
                        output_config[device_id] = {"device_id": device_id, "edge": device_config}
                        if circuits_only:
                            LOG.info(
                                "Device %s summary: %s circuits to be deconfigured (circuits-only mode)",
                                device_name,
                                circuits_deconfigured,
                            )
                        else:
                            LOG.info(
                                "Device %s summary: %s circuits and %s interfaces to be deconfigured",
                                device_name,
                                circuits_deconfigured,
                                interfaces_deconfigured,
                            )
                        LOG.info("Final config for %s: %s", device_name, device_config)
                    else:
                        LOG.info("Device %s: All interfaces already deconfigured or not configured", device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                    LOG.error("Exception type: %s", type(e).__name__)
                    import traceback

                    LOG.error("Full traceback: %s", traceback.format_exc())
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                if circuits_only:
                    LOG.info(
                        "Successfully deconfigured circuits for %s devices (circuits-only mode)", len(output_config)
                    )
                else:
                    LOG.info("Successfully deconfigured interfaces and circuits for %s devices", len(output_config))
            else:
                if circuits_only:
                    LOG.warning("No valid circuit configurations found")
                else:
                    LOG.warning("No valid device configurations found")

            # Summary with explicit lists (consistent with global_config deconfigure logging)
            deconfigured_names = [
                "%s:%s%s" % (e.get("device", ""), e.get("interface", ""), (".%s" % e["vlan"]) if e.get("vlan") else "")
                for e in result["deconfigured_interfaces"]
            ]
            skipped_names = [
                "%s:%s%s (%s)"
                % (
                    e.get("device", ""),
                    e.get("interface", ""),
                    (".%s" % e["vlan"]) if e.get("vlan") else "",
                    e.get("reason", ""),
                )
                for e in result["skipped_interfaces"]
            ]
            LOG.info(
                "Deconfigure completed: deconfigured_interfaces=%s, skipped_interfaces=%s",
                deconfigured_names,
                skipped_names,
            )

            return result

        except Exception as e:
            LOG.error("Error in interface and circuit deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            import traceback

            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"Interface and circuit deconfiguration failed: {str(e)}")

    def configure_interfaces(self, interface_config_file: str, circuit_config_file=None) -> dict:
        """
        Configure all interfaces and circuits for multiple devices concurrently.
        This method calls the configure method to handle all configurations in a single API call per device.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self.configure(interface_config_file, circuit_config_file)

    def deconfigure_interfaces(
        self, interface_config_file: str, circuit_config_file=None, circuits_only: bool = False
    ) -> dict:
        """
        Deconfigure all interfaces and circuits for multiple devices concurrently.
        For WAN interfaces, circuit detachment may be treated by the backend as a "circuit removal" operation.
        If the referenced circuit still has static routes, that detachment can fail with:
        `error removing circuit "<name>". Remove static routes first.`

        To prevent this, this orchestrator performs a two-stage flow when `circuits_only=False`:
        - Stage 1: remove static routes from referenced circuits (idempotent)
        - Stage 2: deconfigure interfaces (reset WAN/LAN parents to default LAN, delete subinterfaces as needed)

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only deconfigure circuits, skip interface deconfiguration

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        # Circuits-only mode is effectively "remove static routes from referenced circuits".
        if circuits_only:
            return self.deconfigure_wan_circuits_interfaces(
                interface_config_file=interface_config_file,
                circuit_config_file=circuit_config_file,
                circuits_only=True,
            )

        # Stage 1: ensure no static routes remain on referenced circuits before detaching WAN interfaces.
        stage1 = self.deconfigure_wan_circuits_interfaces(
            interface_config_file=interface_config_file,
            circuit_config_file=circuit_config_file,
            circuits_only=True,
        )

        # Stage 2: deconfigure interfaces (LAN + WAN).
        stage2 = self.deconfigure(interface_config_file, circuit_config_file, circuits_only=False)

        # Merge results: surface circuit-route work alongside interface work.
        merged = stage2
        merged["changed"] = bool(stage1.get("changed") or stage2.get("changed"))
        merged["deconfigured_devices"] = sorted(
            set(stage1.get("deconfigured_devices", [])) | set(stage2.get("deconfigured_devices", []))
        )
        merged["deconfigured_circuits"] = stage1.get("deconfigured_circuits", [])
        merged["skipped_circuits"] = stage1.get("skipped_circuits", [])
        return merged

    def configure_circuits(self, circuit_config_file: str, interface_config_file: str) -> dict:
        """
        Configure circuits only for multiple devices concurrently.
        This method uses configure_wan_circuits_interfaces with circuits_only=True.
        Only circuits referenced in the interface config will be configured.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info(
            "Configuring circuits only using circuit config: %s and interface config: %s",
            circuit_config_file,
            interface_config_file,
        )
        return self.configure_wan_circuits_interfaces(circuit_config_file, interface_config_file, circuits_only=True)

    def deconfigure_circuits(self, circuit_config_file: str, interface_config_file: str) -> dict:
        """
        Deconfigure circuits only (static routes) for multiple devices concurrently (idempotent).

        This operation removes static routes from the referenced circuits. It checks the current
        device state first, and skips the configuration push when there are no matching static routes
        to delete (returns `changed: False`).

        This method uses deconfigure_wan_circuits_interfaces with circuits_only=True.
        Only circuits referenced in the interface config will be deconfigured.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and per-circuit details.
                  Includes `deconfigured_circuits` and `skipped_circuits` when available.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info(
            "Deconfiguring circuits only using circuit config: %s and interface config: %s",
            circuit_config_file,
            interface_config_file,
        )
        return self.deconfigure_wan_circuits_interfaces(interface_config_file, circuit_config_file, circuits_only=True)

    def configure_lan_interfaces(self, interface_config_file: str) -> dict:
        """
        Configure LAN interfaces for multiple devices concurrently.
        Only interfaces with 'lan' key will be configured.

        The API does not allow moving an interface to a different LAN segment in the same
        request as other interface config changes. So when any interface/subinterface has
        only its segment (lan) changed, we push in two phases: first a segment-only payload,
        then the full config.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            config_data = self.render_config_file(interface_config_file)
            output_config = {}
            device_infos = {}  # device_id -> gcs device info for segment-change detection

            if "interfaces" not in config_data:
                LOG.warning("No interfaces configuration found in %s", interface_config_file)
                return result

            for device_info in config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise ConfigurationError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )
                        device_config: Dict[str, Any] = {"interfaces": {}}

                        lan_interfaces_configured = 0
                        for config in config_list:
                            # Check if this interface has any LAN configuration (main interface or subinterfaces)
                            has_lan_main = config.get("lan") is not None
                            lan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(config):
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found LAN subinterface '%s.%s' for device: %s",
                                        config.get("name"),
                                        sub_interface.get("vlan"),
                                        device_name,
                                    )

                            # Process this interface if it has any LAN configuration
                            if has_lan_main or lan_subinterfaces:
                                if has_lan_main and lan_subinterfaces:
                                    # Both main interface and subinterfaces have LAN config
                                    combined_config = config.copy()
                                    combined_config["sub_interfaces"] = lan_subinterfaces
                                    self.config_utils.device_interface(device_config, action="add", **combined_config)
                                    lan_interfaces_configured += 1 + len(lan_subinterfaces)
                                    LOG.info(
                                        " ✓ To configure LAN main interface '%s' and %s LAN "
                                        "subinterfaces for device: %s",
                                        config.get("name"),
                                        len(lan_subinterfaces),
                                        device_name,
                                    )

                                elif has_lan_main:
                                    # Only main interface has LAN config
                                    main_config = config.copy()
                                    main_config.pop("sub_interfaces", None)  # Remove subinterfaces (both param names)
                                    main_config.pop("subinterfaces", None)
                                    self.config_utils.device_interface(device_config, action="add", **main_config)
                                    lan_interfaces_configured += 1
                                    LOG.info(
                                        " ✓ To configure LAN main interface '%s' for device: %s",
                                        config.get("name"),
                                        device_name,
                                    )

                                elif lan_subinterfaces:
                                    # Only subinterfaces have LAN config - create minimal config
                                    subinterface_config = {
                                        "name": config.get("name"),
                                        "sub_interfaces": lan_subinterfaces,
                                    }
                                    self.config_utils.device_interface(
                                        device_config, action="add", **subinterface_config
                                    )
                                    lan_interfaces_configured += len(lan_subinterfaces)
                                    LOG.info(
                                        " ✓ Configure %s LAN subinterfaces for interface '%s' on device: %s",
                                        len(lan_subinterfaces),
                                        config.get("name"),
                                        device_name,
                                    )
                            else:
                                LOG.info(" ✗ Skipping interface '%s' - no LAN configuration found", config.get("name"))

                        # Check if any LAN interfaces were configured for this device
                        # Note: This check is inside the loop to evaluate after processing all configs for this device
                        if lan_interfaces_configured > 0:
                            output_config[device_id] = {"device_id": device_id, "edge": device_config}
                            device_infos[device_id] = self.gsdk.get_device_info(device_id)
                            LOG.info(
                                "Device %s summary: %s LAN interfaces to be configured",
                                device_name,
                                lan_interfaces_configured,
                            )
                        else:
                            LOG.info("Device %s: No LAN interfaces found to configure", device_name)

                    except DeviceNotFoundError:
                        LOG.error("Device not found: %s", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error configuring LAN interfaces for device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"LAN interface configuration failed for {device_name}: {str(e)}")

            if output_config:
                # Build stage1 (segment-only) payloads for devices where an interface is moved to a new LAN.
                # API rejects moving segment and changing other interface config in the same request.
                _EMPTY_SEGMENT: Dict[str, Any] = {
                    "networks": [],
                    "bgpRedistribution": {},
                    "bgpNeighbors": {},
                    "syslogTargets": {},
                    "staticRoutes": {},
                    "dhcpSubnets": {},
                    "bgpAggregations": {},
                    "ipfixExporters": {},
                }
                stage1_config: Dict[str, Any] = {}
                for device_id, entry in output_config.items():
                    device_config = entry["edge"]
                    gcs_info = device_infos.get(device_id)
                    if not gcs_info:
                        continue
                    # list of (interface_name, vlan or None, new_lan)
                    segment_changes: List[Tuple[str, Optional[int], Any]] = []
                    for ifname, ifdata in device_config.get("interfaces", {}).items():
                        inner = ifdata.get("interface", {})
                        # Main interface LAN: detect segment change whenever config has 'lan'
                        # (with or without subinterfaces)
                        intended_main_lan = inner.get("lan")
                        if intended_main_lan:
                            current_main_lan = self._get_interface_lan(gcs_info, ifname)
                            if current_main_lan is not None and current_main_lan != intended_main_lan:
                                segment_changes.append((ifname, None, intended_main_lan))
                        # Subinterface LANs
                        subinterfaces = inner.get("subinterfaces")
                        if subinterfaces:
                            for vlan_str, sub in subinterfaces.items():
                                intended_lan = sub.get("interface", {}).get("lan")
                                if not intended_lan:
                                    continue
                                current_lan = self._get_subinterface_lan(gcs_info, ifname, int(vlan_str))
                                if current_lan is not None and current_lan != intended_lan:
                                    segment_changes.append((ifname, int(vlan_str), intended_lan))
                    if not segment_changes:
                        continue
                    stage1_edge: Dict[str, Any] = {"interfaces": {}, "segments": {}}
                    for ifname, vlan, new_lan in segment_changes:
                        stage1_edge["segments"][new_lan] = _EMPTY_SEGMENT.copy()
                        if vlan is None:
                            stage1_edge["interfaces"][ifname] = {"interface": {"lan": new_lan}}
                        else:
                            if ifname not in stage1_edge["interfaces"]:
                                stage1_edge["interfaces"][ifname] = {"interface": {"subinterfaces": {}}}
                            # Interface may already exist from main-interface segment change;
                            # ensure subinterfaces exists
                            stage1_edge["interfaces"][ifname]["interface"].setdefault("subinterfaces", {})[
                                str(vlan)
                            ] = {"interface": {"vlan": vlan, "lan": new_lan}}
                    stage1_config[device_id] = {"device_id": device_id, "edge": stage1_edge}
                if stage1_config:
                    LOG.info(
                        "Pushing segment-only update first for %s device(s) (LAN move), then full config",
                        len(stage1_config),
                    )
                    self.execute_concurrent_tasks(self.gsdk.put_device_config, stage1_config)
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["configured_devices"] = list(output_config.keys())
                LOG.info("Successfully configured LAN interfaces for %s devices", len(output_config))
            else:
                LOG.warning("No LAN interface configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in LAN interface configuration: %s", str(e))
            raise ConfigurationError(f"LAN interface configuration failed: {str(e)}")

    def deconfigure_lan_interfaces(self, interface_config_file: str) -> dict:
        """
        Deconfigure LAN interfaces for multiple devices concurrently (idempotent).

        Behavior:
          - If the *parent* interface has a `lan` key in the config, deconfigure means "reset the
            parent to the enterprise default LAN" (and delete any listed LAN subinterfaces).
          - If the config only contains LAN subinterfaces under a parent, deconfigure deletes only
            those subinterfaces and does NOT reset the parent (important for ethernet parents that
            are allowed to remain on the default LAN).

        The method checks if interfaces/subinterfaces exist before attempting deletion.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations

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
            config_data = self.render_config_file(interface_config_file)
            output_config = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            if "interfaces" not in config_data:
                LOG.warning("No interfaces configuration found in %s", interface_config_file)
                return result

            for device_info in config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise ConfigurationError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )

                        # Get device info for idempotency check
                        gcs_device_info = self.gsdk.get_device_info(device_id)

                        device_config: Dict[str, Any] = {"interfaces": {}}

                        lan_interfaces_deconfigured = 0
                        for config in config_list:
                            # Check if this interface has any LAN configuration (main interface or subinterfaces)
                            has_lan_main = config.get("lan") is not None
                            lan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(config):
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found LAN subinterface '%s.%s' for device: %s",
                                        config.get("name"),
                                        sub_interface.get("vlan"),
                                        device_name,
                                    )

                            # Process this interface if it has any LAN configuration
                            if has_lan_main or lan_subinterfaces:
                                interface_name = config.get("name")
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                # In LAN deconfigure workflow for ethernet interfaces:
                                # - If the *parent* interface has a LAN config (`lan` key), deconfigure means
                                #   reset parent interface to default LAN (and optionally delete listed subinterfaces).
                                # - If the config only mentions LAN subinterfaces, we should ONLY delete those
                                #   subinterfaces and MUST NOT reset the parent (the parent may
                                #   already be in default LAN).
                                parent_should_default = main_interface_exists and has_lan_main
                                main_needs_reset = parent_should_default and (current_lan != default_lan)

                                if has_lan_main and not main_interface_exists:
                                    LOG.info(
                                        " ✗ LAN main interface '%s' does not exist on %s, skipping",
                                        interface_name,
                                        device_name,
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": interface_name,
                                            "vlan": None,
                                            "reason": "Interface does not exist",
                                        }
                                    )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in lan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        LOG.info(
                                            " ✓ LAN subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ LAN subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if not needs_deconfigure:
                                    if parent_should_default and current_lan == default_lan:
                                        LOG.info(
                                            " ✓ LAN interface '%s' already deconfigured on %s (parent on %s), skipping",
                                            interface_name,
                                            device_name,
                                            default_lan,
                                        )
                                    continue

                                # Build a minimal delete payload that matches UI behavior:
                                # - parent interface LAN set to default-<enterpriseId>
                                # - subinterfaces deleted (if any exist)
                                payload_config = {"name": interface_name}
                                if parent_should_default:
                                    # Any truthy value triggers template to set parent LAN to default_lan
                                    payload_config["lan"] = True
                                if existing_subinterfaces:
                                    payload_config["sub_interfaces"] = existing_subinterfaces

                                self.config_utils.device_interface(
                                    device_config, action="delete", default_lan=default_lan, **payload_config
                                )

                                lan_interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                    existing_subinterfaces
                                )

                                if main_needs_reset:
                                    LOG.info(
                                        " ✓ To deconfigure LAN main interface '%s' (set to %s) for device: %s",
                                        interface_name,
                                        default_lan,
                                        device_name,
                                    )
                                    result["deconfigured_interfaces"].append(
                                        {"device": device_name, "interface": interface_name, "vlan": None}
                                    )
                                if existing_subinterfaces:
                                    LOG.info(
                                        " ✓ To deconfigure %s LAN subinterfaces for interface '%s' on device: %s",
                                        len(existing_subinterfaces),
                                        interface_name,
                                        device_name,
                                    )
                                    for sub_intf in existing_subinterfaces:
                                        result["deconfigured_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": sub_intf.get("vlan"),
                                            }
                                        )
                            else:
                                LOG.info(" ✗ Skipping interface '%s' - no LAN configuration found", config.get("name"))

                        # Only add to output_config if there's something to deconfigure
                        if device_config.get("interfaces"):
                            if lan_interfaces_deconfigured > 0:
                                output_config[device_id] = {"device_id": device_id, "edge": device_config}
                                LOG.info(
                                    "Device %s summary: %s LAN interfaces to be deconfigured",
                                    device_name,
                                    lan_interfaces_deconfigured,
                                )
                            else:
                                LOG.info("Device %s: No LAN interfaces found to deconfigure", device_name)
                        else:
                            LOG.info("Device %s: All interfaces already deconfigured or not configured", device_name)

                    except DeviceNotFoundError:
                        LOG.error("Device not found: %s", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring LAN interfaces for device %s: %s", device_name, str(e))
                        LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                        LOG.error("Exception type: %s", type(e).__name__)
                        import traceback

                        LOG.error("Full traceback: %s", traceback.format_exc())
                        raise ConfigurationError(f"LAN interface deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info("Successfully deconfigured LAN interfaces for %s devices", len(output_config))
            else:
                LOG.info(
                    "No LAN changes needed - all interfaces already deconfigured or not configured (changed: %s)",
                    result["changed"],
                )

            return result

        except Exception as e:
            LOG.error("Error in LAN interface deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            import traceback

            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"LAN interface deconfiguration failed: {str(e)}")

    def configure_wan_circuits_interfaces(
        self, circuit_config_file: str, interface_config_file: str, circuits_only: bool = False
    ) -> dict:
        """
        Configure WAN circuits and WAN interfaces for multiple devices concurrently.

        Only circuits referenced by the interface configuration (main interface or subinterfaces)
        are included in the payload.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations
            circuits_only: If True, only configure referenced circuits (skip interface configuration)

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            # Load circuit configurations
            circuit_config_data = self.render_config_file(circuit_config_file)
            interface_config_data = self.render_config_file(interface_config_file)

            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            if "interfaces" in interface_config_data:
                for device_info in interface_config_data.get("interfaces") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device
            if "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

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
                    output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}, "circuits": {}}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    if circuits_only:
                        LOG.info(
                            "[configure_wan_circuits_interfaces] Processing device: %s (ID: %s) - CIRCUITS ONLY MODE",
                            device_name,
                            device_id,
                        )
                    else:
                        LOG.info(
                            "[configure_wan_circuits_interfaces] Processing device: %s (ID: %s)", device_name, device_id
                        )
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device
                    circuits_configured = 0
                    for circuit_config in configs.get("circuits", []):
                        if circuit_config.get("circuit") in referenced_circuits:
                            self.config_utils.device_circuit(
                                output_config[device_id]["edge"], action="add", **circuit_config
                            )
                            circuits_configured += 1
                            LOG.info(
                                " ✓ To configure circuit '%s' for device: %s",
                                circuit_config.get("circuit"),
                                device_name,
                            )
                        else:
                            LOG.info(
                                " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                circuit_config.get("circuit"),
                            )

                    # Process interfaces for this device (only if not circuits_only)
                    interfaces_configured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # Check if this interface has any WAN configuration (main interface or subinterfaces)
                            has_wan_main = interface_config.get("circuit") is not None
                            wan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found WAN subinterface '%s.%s' with circuit '%s' for device: %s",
                                        interface_config.get("name"),
                                        sub_interface.get("vlan"),
                                        sub_interface.get("circuit"),
                                        device_name,
                                    )

                            # Process this interface if it has any WAN configuration
                            if has_wan_main or wan_subinterfaces:
                                if has_wan_main and wan_subinterfaces:
                                    # Both main interface and subinterfaces have WAN config
                                    combined_config = interface_config.copy()
                                    combined_config["sub_interfaces"] = wan_subinterfaces
                                    self.config_utils.device_interface(
                                        output_config[device_id]["edge"], action="add", **combined_config
                                    )
                                    interfaces_configured += 1 + len(wan_subinterfaces)
                                    LOG.info(
                                        " ✓ To configure WAN main interface '%s' with circuit '%s' "
                                        "and %s WAN subinterfaces for device: %s",
                                        interface_config.get("name"),
                                        interface_config.get("circuit"),
                                        len(wan_subinterfaces),
                                        device_name,
                                    )

                                elif has_wan_main:
                                    # Only main interface has WAN config
                                    main_config = interface_config.copy()
                                    main_config.pop("sub_interfaces", None)  # Remove subinterfaces (both param names)
                                    main_config.pop("subinterfaces", None)
                                    self.config_utils.device_interface(
                                        output_config[device_id]["edge"], action="add", **main_config
                                    )
                                    interfaces_configured += 1
                                    LOG.info(
                                        " ✓ To configure WAN main interface '%s' with circuit '%s' for device: %s",
                                        interface_config.get("name"),
                                        interface_config.get("circuit"),
                                        device_name,
                                    )

                                elif wan_subinterfaces:
                                    # Only subinterfaces have WAN config - create minimal config
                                    subinterface_config = {
                                        "name": interface_config.get("name"),
                                        "sub_interfaces": wan_subinterfaces,
                                    }
                                    self.config_utils.device_interface(
                                        output_config[device_id]["edge"], action="add", **subinterface_config
                                    )
                                    interfaces_configured += len(wan_subinterfaces)
                                    LOG.info(
                                        " ✓ Configure %s WAN subinterfaces for interface '%s' on device: %s",
                                        len(wan_subinterfaces),
                                        interface_config.get("name"),
                                        device_name,
                                    )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )

                    if circuits_only:
                        LOG.info(
                            "Device %s summary: %s circuits configured (circuits-only mode)",
                            device_name,
                            circuits_configured,
                        )
                    else:
                        LOG.info(
                            "Device %s summary: %s circuits, %s WAN interfaces to be configured",
                            device_name,
                            circuits_configured,
                            interfaces_configured,
                        )
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
                if circuits_only:
                    LOG.info("Successfully configured circuits for %s devices (circuits-only mode)", len(output_config))
                else:
                    LOG.info("Successfully configured circuits and interfaces for %s devices", len(output_config))
            else:
                if circuits_only:
                    LOG.warning("No circuit configurations to apply")
                else:
                    LOG.warning("No circuit or interface configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in WAN circuits and interfaces configuration: %s", str(e))
            raise ConfigurationError(f"WAN circuits and interfaces configuration failed: {str(e)}")

    def deconfigure_wan_circuits_interfaces(
        self, interface_config_file: str, circuit_config_file=None, circuits_only: bool = False
    ) -> dict:
        """
        Deconfigure WAN interfaces and/or circuit static routes for multiple devices concurrently (idempotent).

        - If `circuits_only` is True: only deconfigure circuit static routes (skip interface deconfiguration).
          Static route deletion is idempotent: routes are removed only if they currently exist on the device.
        - If `circuits_only` is False: deconfigure WAN interfaces (circuits may be affected implicitly by the platform).

        For idempotency, this method checks for current interface/subinterface existence and for circuit static routes
        (via `gsdk.get_device_info`) before building a delete payload.

        Ordering:
          - This method performs a two-stage WAN workflow when `circuits_only=False`:
            1) Remove static routes from referenced circuits (if any exist)
            2) Reset WAN interfaces to enterprise default LAN and detach circuits
          - This avoids backend failures when detaching a circuit that still has static routes.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only deconfigure circuits, skip interface deconfiguration

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces.
                  When `circuits_only=True`, also includes `deconfigured_circuits` and `skipped_circuits`.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "deconfigured_interfaces": [],
            "skipped_interfaces": [],
            "deconfigured_circuits": [],
            "skipped_circuits": [],
        }

        try:
            interface_config_data = self.render_config_file(interface_config_file)

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            # Two-stage workflow:
            # 1) Remove circuit static routes for referenced WAN circuits (if any).
            # 2) Reset WAN interface(s) to default LAN and detach circuits.
            #
            # The backend can treat detaching a circuit from a WAN interface as a "circuit removal"
            # operation and will fail if static routes still exist on that circuit.
            output_config_circuits = {}
            output_config_interfaces = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            if "interfaces" in interface_config_data:
                for device_info in interface_config_data.get("interfaces") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

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

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info(
                        "[deconfigure_wan_circuits_interfaces] Processing device: %s (ID: %s)", device_name, device_id
                    )
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Build separate payloads for circuits vs interfaces to enforce ordering.
                    device_circuit_config: Dict[str, Any] = {}
                    device_interface_config: Dict[str, Any] = {}

                    # Process circuits for this device (static route deconfiguration)
                    circuits_deconfigured = 0
                    if configs.get("circuits"):
                        device_circuit_config.setdefault("circuits", {})
                        for circuit_config in configs.get("circuits", []):
                            circuit_name = circuit_config.get("circuit")
                            if circuit_name not in referenced_circuits:
                                LOG.info(" ✗ Skipping circuit '%s' - not referenced in interface configs", circuit_name)
                                continue

                            existing_prefixes = self._get_circuit_static_route_prefixes(gcs_device_info, circuit_name)
                            LOG.info(
                                "[circuits-idempotency] %s/%s circuit '%s' existing static route prefixes: %s",
                                device_name,
                                device_id,
                                circuit_name,
                                sorted(existing_prefixes),
                            )

                            # If static_routes are specified in YAML, delete only those (and only if they exist).
                            # If none specified, interpret deconfigure as "remove any existing static routes".
                            static_routes_cfg = circuit_config.get("static_routes") or {}

                            if static_routes_cfg:
                                requested_prefixes = (
                                    set(static_routes_cfg.keys()) if isinstance(static_routes_cfg, dict) else set()
                                )
                                prefixes_to_delete = sorted(requested_prefixes & existing_prefixes)
                                missing_prefixes = sorted(requested_prefixes - existing_prefixes)
                                LOG.info(
                                    "[circuits-idempotency] %s/%s circuit '%s' requested=%s will_delete=%s missing=%s",
                                    device_name,
                                    device_id,
                                    circuit_name,
                                    sorted(requested_prefixes),
                                    prefixes_to_delete,
                                    missing_prefixes,
                                )
                                for prefix in missing_prefixes:
                                    result["skipped_circuits"].append(
                                        {
                                            "device": device_name,
                                            "circuit": circuit_name,
                                            "prefix": prefix,
                                            "reason": "Static route does not exist",
                                        }
                                    )
                            else:
                                prefixes_to_delete = sorted(existing_prefixes)
                                LOG.info(
                                    "[circuits-idempotency] %s/%s circuit '%s' no static_routes in "
                                    "YAML; will_delete_all_existing=%s",
                                    device_name,
                                    device_id,
                                    circuit_name,
                                    prefixes_to_delete,
                                )

                            if not prefixes_to_delete:
                                LOG.info(
                                    " ✓ No static route changes needed for circuit '%s' on %s, skipping",
                                    circuit_name,
                                    device_name,
                                )
                                result["skipped_circuits"].append(
                                    {
                                        "device": device_name,
                                        "circuit": circuit_name,
                                        "prefix": None,
                                        "reason": "Static routes already deconfigured",
                                    }
                                )
                                continue

                            delete_circuit_config = circuit_config.copy()
                            # Template expects static_routes dict keyed by prefix; values can be empty for delete.
                            delete_circuit_config["static_routes"] = {p: {} for p in prefixes_to_delete}
                            LOG.info(
                                "[circuits-idempotency] %s/%s circuit '%s' building delete payload for prefixes=%s",
                                device_name,
                                device_id,
                                circuit_name,
                                prefixes_to_delete,
                            )

                            self.config_utils.device_circuit(
                                device_circuit_config, action="delete", **delete_circuit_config
                            )
                            circuits_deconfigured += 1
                            result["deconfigured_circuits"].append(
                                {"device": device_name, "circuit": circuit_name, "static_routes": prefixes_to_delete}
                            )
                            LOG.info(
                                " ✓ To deconfigure %s static routes on circuit '%s' for device: %s",
                                len(prefixes_to_delete),
                                circuit_name,
                                device_name,
                            )

                    # Process interfaces for this device - skip if circuits_only=True
                    interfaces_deconfigured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # Check if this interface has any WAN configuration (main interface or subinterfaces)
                            has_wan_main = interface_config.get("circuit") is not None
                            wan_subinterfaces = []
                            interface_name = interface_config.get("name")

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found WAN subinterface '%s.%s' with circuit '%s' for device: %s",
                                        interface_name,
                                        sub_interface.get("vlan"),
                                        sub_interface.get("circuit"),
                                        device_name,
                                    )

                            # Process this interface if it has any WAN configuration
                            if has_wan_main or wan_subinterfaces:
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                current_circuit = (
                                    self._get_interface_circuit(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )

                                # For ethernet WAN: "deconfigure main" means reset parent to default
                                # LAN and clear circuit.
                                # Only do that when needed (state-aware idempotency).
                                main_needs_reset = (
                                    has_wan_main
                                    and main_interface_exists
                                    and ((current_lan != default_lan) or (current_circuit is not None))
                                )

                                # Check if main interface exists (if it has WAN config)
                                if has_wan_main:
                                    if main_interface_exists:
                                        if main_needs_reset:
                                            LOG.info(
                                                " ✓ WAN main interface '%s' exists on %s "
                                                "(lan=%s circuit=%s), will reset to %s",
                                                interface_name,
                                                device_name,
                                                current_lan,
                                                current_circuit,
                                                default_lan,
                                            )
                                        else:
                                            LOG.info(
                                                " ✓ WAN main interface '%s' already deconfigured "
                                                "on %s (lan=%s circuit=%s), skipping parent reset",
                                                interface_name,
                                                device_name,
                                                current_lan,
                                                current_circuit,
                                            )
                                    else:
                                        LOG.info(
                                            " ✗ WAN main interface '%s' does not exist on %s, skipping",
                                            interface_name,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": None,
                                                "reason": "Interface does not exist",
                                            }
                                        )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in wan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        LOG.info(
                                            " ✓ WAN subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ WAN subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if not needs_deconfigure:
                                    # Nothing to do: parent already reset and no subinterfaces exist
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": interface_name,
                                            "vlan": None,
                                            "reason": "WAN interface already deconfigured",
                                        }
                                    )
                                    continue

                                if needs_deconfigure:
                                    device_interface_config.setdefault("interfaces", {})
                                    if has_wan_main and existing_subinterfaces:
                                        # Both main interface and subinterfaces have WAN config
                                        combined_config = interface_config.copy()
                                        combined_config["sub_interfaces"] = existing_subinterfaces
                                        # If parent is already reset, don't include circuit in payload;
                                        # just delete subinterfaces.
                                        if has_wan_main and not main_needs_reset:
                                            combined_config.pop("circuit", None)
                                        self.config_utils.device_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **combined_config,
                                        )
                                        interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                            existing_subinterfaces
                                        )
                                        if main_needs_reset:
                                            LOG.info(
                                                " ✓ To reset WAN main interface '%s' to %s and "
                                                "deconfigure %s WAN subinterfaces for device: %s",
                                                interface_name,
                                                default_lan,
                                                len(existing_subinterfaces),
                                                device_name,
                                            )
                                            result["deconfigured_interfaces"].append(
                                                {"device": device_name, "interface": interface_name, "vlan": None}
                                            )
                                        else:
                                            LOG.info(
                                                " ✓ To deconfigure %s WAN subinterfaces for interface "
                                                "'%s' on device: %s (parent already reset)",
                                                len(existing_subinterfaces),
                                                interface_name,
                                                device_name,
                                            )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )

                                    elif has_wan_main and main_needs_reset:
                                        # Only main interface needs reset (idempotent)
                                        main_config = interface_config.copy()
                                        main_config.pop(
                                            "sub_interfaces", None
                                        )  # Remove subinterfaces (both param names)
                                        main_config.pop("subinterfaces", None)
                                        device_interface_config.setdefault("interfaces", {})
                                        self.config_utils.device_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **main_config,
                                        )
                                        interfaces_deconfigured += 1
                                        LOG.info(
                                            " ✓ To deconfigure WAN main interface '%s' with circuit "
                                            "'%s' for device: %s",
                                            interface_name,
                                            interface_config.get("circuit"),
                                            device_name,
                                        )
                                        result["deconfigured_interfaces"].append(
                                            {"device": device_name, "interface": interface_name, "vlan": None}
                                        )

                                    elif existing_subinterfaces:
                                        # Only subinterfaces have WAN config - create minimal config
                                        subinterface_config = {
                                            "name": interface_name,
                                            "sub_interfaces": existing_subinterfaces,
                                        }
                                        device_interface_config.setdefault("interfaces", {})
                                        self.config_utils.device_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **subinterface_config,
                                        )
                                        interfaces_deconfigured += len(existing_subinterfaces)
                                        LOG.info(
                                            " ✓ Deconfigure %s WAN subinterfaces for interface '%s' on device: %s",
                                            len(existing_subinterfaces),
                                            interface_name,
                                            device_name,
                                        )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )
                    else:
                        LOG.info(" ✓ Skipping WAN interface deconfiguration (circuits-only mode)")

                    # Stage 1 (circuits): only if we have any static routes to remove
                    if device_circuit_config.get("circuits"):
                        output_config_circuits[device_id] = {"device_id": device_id, "edge": device_circuit_config}
                        LOG.info(
                            "Device %s summary (stage1): %s circuits with static routes to be deconfigured",
                            device_name,
                            circuits_deconfigured,
                        )
                        LOG.info("Final circuits config for %s: %s", device_name, device_circuit_config)
                    else:
                        LOG.info("Device %s (stage1): No circuit static route changes needed", device_name)

                    # Stage 2 (interfaces): only if interface changes exist and we're not in circuits-only mode
                    if not circuits_only and device_interface_config.get("interfaces"):
                        output_config_interfaces[device_id] = {"device_id": device_id, "edge": device_interface_config}
                        LOG.info(
                            "Device %s summary (stage2): %s WAN interfaces to be deconfigured",
                            device_name,
                            interfaces_deconfigured,
                        )
                        LOG.info("Final interfaces config for %s: %s", device_name, device_interface_config)
                    else:
                        if circuits_only:
                            LOG.info("Device %s (stage2): skipped (circuits-only mode)", device_name)
                        else:
                            LOG.info("Device %s (stage2): No WAN interface changes needed", device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                    LOG.error("Exception type: %s", type(e).__name__)
                    import traceback

                    LOG.error("Full traceback: %s", traceback.format_exc())
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            # Execute stage 1 first (remove static routes), then stage 2 (detach circuits / reset WAN interfaces).
            if output_config_circuits:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config_circuits)
                result["changed"] = True
                LOG.info(
                    "Successfully deconfigured circuit static routes for %s devices (stage1)",
                    len(output_config_circuits),
                )

            if output_config_interfaces:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config_interfaces)
                result["changed"] = True
                LOG.info(
                    "Successfully deconfigured WAN interfaces for %s devices (stage2)", len(output_config_interfaces)
                )

            deconfigured_device_ids = sorted(set(output_config_circuits.keys()) | set(output_config_interfaces.keys()))
            if deconfigured_device_ids:
                result["deconfigured_devices"] = deconfigured_device_ids
            else:
                LOG.info(
                    "No changes needed - all circuits/routes and interfaces already deconfigured (changed: %s)",
                    result["changed"],
                )

            return result

        except Exception as e:
            LOG.error("Error in WAN circuits and interfaces deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            import traceback

            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"WAN circuits and interfaces deconfiguration failed: {str(e)}")
