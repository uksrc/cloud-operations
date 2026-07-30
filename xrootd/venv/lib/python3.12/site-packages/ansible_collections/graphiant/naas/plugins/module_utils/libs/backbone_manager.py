"""
Backbone (Core) Interface Manager for Graphiant Playbooks.

This module handles backbone (Core) interface, circuit, site, and per-VRF
syslog target configuration management.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Tuple

from .base_manager import BaseManager
from .interface_manager import InterfaceManager
from .logger import setup_logger
from .site_manager import SiteManager
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()

# Interface type discriminators understood by `backbone_interface_template.yaml`.
#
# `p2mp_tunnel` is lifecycle-coupled to its ISP circuit (`circuit: isp-N`) --
# the SDK auto-deletes the tunnel when the circuit is deconfigured. p2mp tunnels
# are therefore configured alongside the WAN circuit
# (`configure_wan_circuits`) and never explicitly
# deconfigured.
CORE_TO_CORE_INTERFACE_TYPES = {"loopback", "core_to_core_link", "disabled"}
CORE_TO_CORE_TUNNEL_TYPES = {"core_to_core_ipsec_tunnel"}
WAN_CIRCUIT_PREFIX = "isp-"
DIRECT_PEER_PREFIX = "direct-peer-"


class BackboneManager(BaseManager):
    """
    Manages backbone (Core) device configuration.

    Handles the configuration and deconfiguration of Core network interfaces,
    circuits, and VRF-specific syslog targets.

    Notes:
        - Configure workflows push configuration via `gsdk.put_device_config` and may not
          be fully idempotent.
        - Deconfigure workflows are designed to be idempotent by checking current device state
          (via `gsdk.get_device_info`) before building delete payloads -- both the parent
          interface and each declared VLAN sub-interface are verified to exist on the device
          before being included in the reset payload.
        - For full backbone payload pushes (`configure_backbone`), the referenced site is
          created idempotently via `gsdk.create_site` before the device push -- otherwise
          `gsdk.put_device_config` is rejected with: `error creating site`.
        - For `core_to_core_ipsec_tunnel` creation, the `tunnel_underlay` interface is
          pre-pushed to ensure it is in an ISP VRF before the tunnel is inserted -- otherwise
          the request is rejected with: `interface_tunnel: provided local interface is the
          incorrect type or not in an ISP VRF`.
    """

    # ------------------------------------------------------------------
    # BaseManager abstract methods
    # ------------------------------------------------------------------

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure backbone (Core) payloads for multiple devices concurrently.

        This method is an alias for `configure_backbone`.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self.configure_backbone(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure backbone (Core) payloads for multiple devices concurrently (idempotent).

        This method is an alias for `deconfigure_backbone`.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self.deconfigure_backbone(config_yaml_file)

    # ------------------------------------------------------------------
    # Helpers: device iteration / payload assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _iter_backbone_devices(config_data: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
        """
        Iterate over (device_name, core_block) tuples from the rendered config.

        Expected shape::

            backbone_devices:
              - <device_name>:
                  core:
                    name: ...
                    regionName: ...
                    site: { ... }
                    interfaces: [ ... ]
                    vrfs: { ... }

        Args:
            config_data: Parsed YAML payload from `render_config_file`

        Yields:
            (device_name, core_block) tuples; entries with missing or non-dict
            `core` blocks are skipped.
        """
        devices = config_data.get("backbone_devices") or []
        for device_entry in devices:
            if not isinstance(device_entry, dict):
                continue
            for device_name, payload in device_entry.items():
                if not isinstance(payload, dict):
                    continue
                core_block = payload.get("core") or {}
                if not isinstance(core_block, dict):
                    continue
                yield device_name, core_block

    def _enterprise_default_lan(self) -> str:
        """Return the enterprise-wide default LAN name (`default-<enterprise_id>`)."""
        try:
            ent_id = self.gsdk.get_enterprise_id()
        except Exception:  # pylint: disable=broad-except
            ent_id = ""
        return f"default-{ent_id}" if ent_id else "default-10000000000"

    @staticmethod
    def _build_site_block(core_block: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a {name, regionName, site} core sub-payload for site_info ops."""
        site_payload: Dict[str, Any] = {}
        if "name" in core_block:
            site_payload["name"] = core_block["name"]
        if "regionName" in core_block:
            site_payload["regionName"] = core_block["regionName"]
        if "site" in core_block:
            site_payload["site"] = core_block["site"]
        return site_payload

    @staticmethod
    def _build_vrfs_syslog_block(core_block: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build `{"vrfs": {<vrf>: {"syslogTargets": {<name>: {"target": {...}}}}}}`
        from a user-friendly input shape.

        Supported input shapes:

        1. List of `{name, target: {...}}` dicts (parity with the top-level
           `syslog_servers` shape -- preferred)::

               vrfs:
                 graphiant-local-management:
                   syslogTargets:
                     - name: "OOB wus3 local-management"
                       target:
                         host: syslog-wus3.graphiant.network
                         port: 514
                         transport: tcp
                         severity: warning
                         serverStatus: true

        2. Dict keyed by target name with inline target body (legacy)::

               vrfs:
                 graphiant-local-management:
                   syslogTargets:
                     "OOB wus3 local-management":
                       enabled: true
                       transport: tcp
                       host: syslog-wus3.graphiant.network
                       port: 514
                       severity: warning

        Returns:
            dict: `{"vrfs": {...}}` payload, or `{}` when no syslog targets are present.
        """
        vrfs_in = core_block.get("vrfs") or {}
        if not isinstance(vrfs_in, dict):
            return {}
        vrfs_out: Dict[str, Any] = {}
        for vrf_name, vrf_cfg in vrfs_in.items():
            if not isinstance(vrf_cfg, dict):
                continue
            syslog_in = vrf_cfg.get("syslogTargets") or vrf_cfg.get("syslog_targets") or {}
            targets_out: Dict[str, Any] = {}
            if isinstance(syslog_in, list):
                # List of {name, target: {...}} dicts.
                for item in syslog_in:
                    if not isinstance(item, dict):
                        continue
                    target_name = item.get("name")
                    if not target_name:
                        continue
                    target_body = item.get("target")
                    if target_body is None:
                        targets_out[target_name] = {"target": None}
                        continue
                    if not isinstance(target_body, dict):
                        continue
                    body = dict(target_body)
                    body.setdefault("name", target_name)
                    targets_out[target_name] = {"target": body}
            elif isinstance(syslog_in, dict):
                # Dict keyed by target name.
                for target_name, target_cfg in syslog_in.items():
                    if target_cfg is None:
                        targets_out[target_name] = {"target": None}
                        continue
                    if not isinstance(target_cfg, dict):
                        continue
                    # If the user already wrapped with {"target": {...}}, pass through.
                    if "target" in target_cfg and isinstance(target_cfg["target"], dict):
                        targets_out[target_name] = {"target": dict(target_cfg["target"])}
                        targets_out[target_name]["target"].setdefault("name", target_name)
                        continue
                    target_body = dict(target_cfg)
                    target_body.setdefault("name", target_name)
                    targets_out[target_name] = {"target": target_body}
            if targets_out:
                vrfs_out[vrf_name] = {"syslogTargets": targets_out}
        return {"vrfs": vrfs_out} if vrfs_out else {}

    def _render_interface(self, interface_cfg: Dict[str, Any], action: str = "add") -> Dict[str, Any]:
        """Render a single interface entry through the backbone Jinja template."""
        if "name" not in interface_cfg:
            raise ConfigurationError("Interface entry missing required 'name' key")
        kwargs = dict(interface_cfg)
        kwargs.setdefault("default_lan", self._enterprise_default_lan())
        rendered: Dict[str, Any] = {"interfaces": {}}
        self.config_utils.device_backbone_interface(rendered, action=action, **kwargs)
        return rendered

    def _build_interfaces_block(
        self,
        interfaces: List[Dict[str, Any]],
        predicate=None,
        action: str = "add",
    ) -> Dict[str, Any]:
        """
        Render a list of interface configs through the template and return
        `{"interfaces": {<name>: {...}}}`. Optional `predicate` filters which
        entries to include (called with the original interface_cfg dict).
        """
        block: Dict[str, Any] = {"interfaces": {}}
        for cfg in interfaces or []:
            if predicate is not None and not predicate(cfg):
                continue
            rendered = self._render_interface(cfg, action=action)
            block["interfaces"].update(rendered.get("interfaces", {}))
        return block

    @staticmethod
    def _get_existing_syslog_targets(gcs_device_info) -> Dict[str, set]:
        """
        Return `{vrf_name: {target_name, ...}}` from a `gsdk.get_device_info` response.

        The SDK exposes the device VRFs as `device.segments` (list of
        `ManaV2Vrf`); each VRF carries a `syslog_targets` list whose entries
        have a `name` attribute.

        Args:
            gcs_device_info: Device info object from `gsdk.get_device_info()`

        Returns:
            dict: `{vrf_name: set(target_name, ...)}`; empty when no targets exist
                  or the device info is unavailable.
        """
        existing: Dict[str, set] = {}
        if gcs_device_info is None or not hasattr(gcs_device_info, "device"):
            return existing
        device = gcs_device_info.device
        if device is None:
            return existing
        vrfs = getattr(device, "segments", None) or getattr(device, "vrfs", None) or []
        for vrf in vrfs:
            vrf_name = getattr(vrf, "name", None)
            if not vrf_name:
                continue
            targets = getattr(vrf, "syslog_targets", None) or []
            names = {getattr(t, "name", None) for t in targets if getattr(t, "name", None)}
            if names:
                existing[vrf_name] = names
        return existing

    # ------------------------------------------------------------------
    # Interface-type predicates
    # ------------------------------------------------------------------

    @staticmethod
    def _is_core_to_core_interface(cfg: Dict[str, Any]) -> bool:
        """True for non-tunnel core-core interfaces (`loopback`, `core_to_core_link`,
        `disabled`)."""
        itype = cfg.get("interface_type")
        if itype in CORE_TO_CORE_INTERFACE_TYPES:
            return True
        if itype:
            # An explicit interface_type is authoritative -- anything declared but
            # not in CORE_TO_CORE_INTERFACE_TYPES is not a core-core interface.
            return False
        # Fallback when interface_type is not set: anything with a `lan` key
        # (graphiant-core or default-<id>) and no `circuit` is treated as core-core.
        if cfg.get("lan") and not cfg.get("circuit"):
            return True
        return False

    @staticmethod
    def _is_core_to_core_tunnel(cfg: Dict[str, Any]) -> bool:
        """True for core-core IPsec tunnel interfaces (`core_to_core_ipsec_tunnel`)."""
        return cfg.get("interface_type") in CORE_TO_CORE_TUNNEL_TYPES

    @staticmethod
    def _is_isp_circuit(cfg: Dict[str, Any]) -> bool:
        """True for ISP transit circuits (`interface_type: isp_circuit` or
        `circuit: isp-*`)."""
        if cfg.get("interface_type") == "isp_circuit":
            return True
        circuit = cfg.get("circuit") or ""
        return isinstance(circuit, str) and circuit.startswith(WAN_CIRCUIT_PREFIX)

    @staticmethod
    def _is_p2mp_tunnel(cfg: Dict[str, Any]) -> bool:
        """
        True for `p2mp_tunnel` entries (e.g. `tunnel-h2h-core-p2mp-isp-N`).

        These are lifecycle-coupled to an ISP circuit and are pushed alongside
        `configure_wan_circuits`; they are auto-deleted by the backend when the
        underlying `circuit: isp-N` is deconfigured, so they are deliberately
        excluded from the WAN deconfigure path.
        """
        return cfg.get("interface_type") == "p2mp_tunnel"

    @classmethod
    def _is_isp_circuit_or_p2mp_tunnel(cls, cfg: Dict[str, Any]) -> bool:
        """OR-predicate used for `configure_wan_circuits`."""
        return cls._is_isp_circuit(cfg) or cls._is_p2mp_tunnel(cfg)

    @staticmethod
    def _is_direct_peer(cfg: Dict[str, Any]) -> bool:
        """True for direct-peer circuits (`interface_type: direct_peer` or
        `circuit: direct-peer-*`)."""
        if cfg.get("interface_type") == "direct_peer":
            return True
        circuit = cfg.get("circuit") or ""
        return isinstance(circuit, str) and circuit.startswith(DIRECT_PEER_PREFIX)

    # ------------------------------------------------------------------
    # Full / site_info operations
    # ------------------------------------------------------------------

    def configure_backbone(self, config_yaml_file: str) -> dict:
        """
        Configure the complete backbone (Core) configuration for multiple devices
        concurrently.

        Orchestrates the per-device push together with the global prerequisites in
        dependency order so that every object a device references is already in
        place when the `gsdk.put_device_config` runs:

          1. `SiteManager.configure` -- create the sites (and attach any
             global objects) referenced by `core.site.name` on each device.
          2. Per-device pre-push of `tunnel_underlay` interfaces (phase 1) so
             `core_to_core_ipsec_tunnel` entries land into an ISP VRF underlay.
             Otherwise the backend rejects the tunnel with
             `interface_tunnel: provided local interface is the incorrect type
             or not in an ISP VRF (SQLSTATE P0001)`.
          3. Per-device full Core payload push (phase 2) -- name, regionName,
             site, interfaces, vrfs.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via `gsdk.put_device_config`. True idempotency would require comparing current
            vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info("[configure_backbone] Orchestrating full backbone configuration via %s", config_yaml_file)

        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            config_data = self.render_config_file(config_yaml_file)

            # Stage 0: Create sites + attach global objects (referenced by device-level core.site.name).
            if config_data.get("sites"):
                LOG.info("[configure_backbone] Stage: configure_sites")
                sites_result = SiteManager(self.config_utils).configure(config_yaml_file)
                if sites_result.get("changed"):
                    result["changed"] = True

            underlay_output: Dict[int, Dict[str, Any]] = {}
            output_config: Dict[int, Dict[str, Any]] = {}

            if "backbone_devices" not in config_data:
                LOG.warning("No backbone_devices configuration found in %s", config_yaml_file)
                return result

            for device_name, core_block in self._iter_backbone_devices(config_data):
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[configure_backbone] Processing device: %s (ID: %s)", device_name, device_id)

                    site_block = self._build_site_block(core_block)
                    interfaces = core_block.get("interfaces") or []

                    # Phase 1 prep: collect tunnel underlay interfaces referenced by core_to_core_ipsec_tunnel entries.
                    underlay_names = {
                        cfg.get("tunnel_underlay") or cfg.get("tunnelUnderlay")
                        for cfg in interfaces
                        if cfg.get("interface_type") == "core_to_core_ipsec_tunnel"
                    }
                    underlay_names.discard(None)
                    underlays_prepared = 0
                    if underlay_names:
                        underlay_cfgs = [cfg for cfg in interfaces if cfg.get("name") in underlay_names]
                        underlay_block = self._build_interfaces_block(underlay_cfgs, predicate=None, action="add")
                        if underlay_block.get("interfaces"):
                            underlay_output[device_id] = {"device_id": device_id, "core": underlay_block}
                            underlays_prepared = len(underlay_block["interfaces"])
                            LOG.info(
                                " ✓ To pre-push %s tunnel underlay interface(s) for device: %s (phase 1)",
                                underlays_prepared,
                                device_name,
                            )

                    # Phase 2 prep: assemble the full core payload.
                    core_payload: Dict[str, Any] = {}
                    core_payload.update(site_block)
                    if "shared" in core_block:
                        core_payload["shared"] = core_block["shared"]
                    if interfaces:
                        rendered = self._build_interfaces_block(interfaces, predicate=None, action="add")
                        core_payload.update(rendered)
                    vrfs_block = self._build_vrfs_syslog_block(core_block)
                    if vrfs_block:
                        core_payload.update(vrfs_block)
                    output_config[device_id] = {"device_id": device_id, "core": core_payload}

                    LOG.info(
                        "Device %s summary: %s interfaces, %s vrfs, %s tunnel underlays to be configured",
                        device_name,
                        len(interfaces),
                        len(vrfs_block.get("vrfs", {})),
                        underlays_prepared,
                    )
                    LOG.info("Final config for %s: %s", device_name, core_payload)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring backbone for device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Backbone configuration failed for {device_name}: {str(e)}")

            # Phase 1: push tunnel underlays first so they enter an ISP VRF.
            if underlay_output:
                LOG.info("Pushing tunnel underlay interfaces first (phase 1) for %s device(s)", len(underlay_output))
                self.execute_concurrent_tasks(self.gsdk.put_device_config, underlay_output)

            # Phase 2: push the complete payload.
            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["configured_devices"] = list(output_config.keys())
                LOG.info("Successfully configured backbone (Core) for %s devices", len(output_config))
            else:
                LOG.warning("No backbone configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in backbone configuration: %s", str(e))
            raise ConfigurationError(f"Backbone configuration failed: {str(e)}")

    def deconfigure_backbone(self, config_yaml_file: str) -> dict:
        """
        Deconfigure the complete backbone (Core) configuration for multiple devices
        concurrently.

        Orchestrates the device-level interface teardown plus the global cleanup
        in reverse dependency order so that no global object is deleted while a
        device still references it:

          1. `deconfigure_wan_circuits` -- reset ISP transit
             circuits. The backend auto-deletes any paired `p2mp_tunnel` entries as a
             side-effect of the circuit reset, so they do not need a separate call.
          2. `deconfigure_direct_peer_interfaces` -- reset direct-peer
             circuits.
          3. `deconfigure_core_to_core_tunnel_interfaces` -- delete IPsec tunnel
             interfaces. Their `tunnel_underlay` ports are now safe to touch since
             the WAN ISP circuits have already been detached.
          4. `deconfigure_core_to_core_interfaces` -- reset loopback / core_link /
             disabled ports to the enterprise default LAN.
          5. `deconfigure_syslog_targets` -- remove per-VRF syslog
             target references from each device's VRFs.
          6. `SiteManager.deconfigure` -- detach any attached global objects
             from sites and delete the sites themselves.

        Each sub-stage is idempotent (checks current device/portal state before
        issuing deletes) -- safe to run multiple times.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Merged result with 'changed' status (OR across stages), union of
                  `deconfigured_devices`, and the combined `skipped_interfaces` and
                  `skipped_targets` lists from the sub-stages.

        Raises:
            ConfigurationError: If configuration processing fails in any sub-stage
            DeviceNotFoundError: If any device cannot be found in any sub-stage
        """
        LOG.info("[deconfigure_backbone] Orchestrating full backbone teardown via %s", config_yaml_file)

        stages = [
            ("deconfigure_wan_circuits_interfaces", self.deconfigure_wan_circuits),
            ("deconfigure_direct_peer_interfaces", self.deconfigure_direct_peer_interfaces),
            ("deconfigure_core_to_core_tunnel_interfaces", self.deconfigure_core_to_core_tunnel_interfaces),
            ("deconfigure_core_to_core_interfaces", self.deconfigure_core_to_core_interfaces),
            ("deconfigure_syslog_targets", self.deconfigure_syslog_targets),
        ]

        merged: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "skipped_interfaces": [],
            "skipped_targets": [],
        }
        devices_union: set = set()

        for stage_name, stage_fn in stages:
            LOG.info("[deconfigure_backbone] Stage: %s", stage_name)
            stage_result = stage_fn(config_yaml_file)
            if stage_result.get("changed"):
                merged["changed"] = True
            devices_union.update(stage_result.get("deconfigured_devices", []))
            merged["skipped_interfaces"].extend(stage_result.get("skipped_interfaces", []))
            merged["skipped_targets"].extend(stage_result.get("skipped_targets", []))

        merged["deconfigured_devices"] = sorted(devices_union)

        LOG.info(
            "Successfully orchestrated backbone teardown: changed=%s, devices=%s, "
            "skipped_interfaces=%s, skipped_targets=%s",
            merged["changed"],
            len(merged["deconfigured_devices"]),
            len(merged["skipped_interfaces"]),
            len(merged["skipped_targets"]),
        )
        return merged

    # ------------------------------------------------------------------
    # Core-core interface operations (loopback + core_link + disabled)
    # ------------------------------------------------------------------

    def configure_core_to_core_interfaces(self, config_yaml_file: str) -> dict:
        """
        Configure core-core interfaces for multiple devices concurrently.

        Pushes `loopback`, `core_to_core_link` (with optional VLAN sub-interfaces),
        and `disabled` default-LAN ports on the `graphiant-core` segment.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._configure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="configure_core_to_core_interfaces",
            predicate=self._is_core_to_core_interface,
            interfaces_log_label="core-core interfaces",
        )

    def deconfigure_core_to_core_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deconfigure core-core interfaces for multiple devices concurrently (idempotent).

        Resets `loopback` / `core_to_core_link` / `disabled` interfaces to the
        enterprise default LAN. Checks current device state via `gsdk.get_device_info`
        and skips interfaces and VLAN sub-interfaces that do not exist on the device --
        safe to run multiple times.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._deconfigure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="deconfigure_core_to_core_interfaces",
            predicate=self._is_core_to_core_interface,
            interfaces_log_label="core-core interfaces",
        )

    # ------------------------------------------------------------------
    # Core-core tunnel interface operations (ipsec_tunnel)
    # ------------------------------------------------------------------

    def configure_core_to_core_tunnel_interfaces(self, config_yaml_file: str) -> dict:
        """
        Configure core-core IPsec tunnel interfaces for multiple devices concurrently.

        Pushes `core_to_core_ipsec_tunnel` interfaces on the `graphiant-core` segment.
        Tunnel underlay interfaces (the physical ports referenced by `tunnel_underlay`)
        must already be in an ISP VRF -- typically configured via
        `configure_wan_circuits` first.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._configure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="configure_core_to_core_tunnel_interfaces",
            predicate=self._is_core_to_core_tunnel,
            interfaces_log_label="core-to-core tunnel interfaces",
        )

    def deconfigure_core_to_core_tunnel_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deconfigure core-core IPsec tunnel interfaces for multiple devices concurrently
        (idempotent).

        Deletes `core_to_core_ipsec_tunnel` interfaces (the Core SDK requires an empty wrapper `{}`
        for tunnel deletion -- handled by the template). Checks current device state via
        `gsdk.get_device_info` and skips tunnels that do not exist on the device --
        safe to run multiple times.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._deconfigure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="deconfigure_core_to_core_tunnel_interfaces",
            predicate=self._is_core_to_core_tunnel,
            interfaces_log_label="core-to-core tunnel interfaces",
        )

    # ------------------------------------------------------------------
    # WAN ISP circuit operations
    # ------------------------------------------------------------------

    def configure_wan_circuits(self, config_yaml_file: str) -> dict:
        """
        Configure WAN ISP circuit interfaces for multiple devices concurrently.

        Pushes ISP transit (`circuit: isp-*`) interfaces along with their paired
        `p2mp_tunnel` entries (`tunnel-h2h-core-p2mp-isp-N`). p2mp tunnels are
        slaved to their ISP circuit lifecycle and must be created explicitly here;
        they are auto-deleted by the backend when the underlying circuit is deconfigured.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._configure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="configure_wan_circuits",
            predicate=self._is_isp_circuit_or_p2mp_tunnel,
            interfaces_log_label="WAN ISP circuit + p2mp tunnel interfaces",
        )

    def deconfigure_wan_circuits(self, config_yaml_file: str) -> dict:
        """
        Deconfigure WAN ISP circuit interfaces for multiple devices concurrently
        (idempotent).

        Resets ISP transit interfaces to the enterprise default LAN. Checks current
        device state via `gsdk.get_device_info` and skips interfaces that do not
        exist on the device -- safe to run multiple times. p2mp tunnels are NOT
        touched here; the backend auto-deletes them when their underlying `circuit: isp-N`
        is deconfigured.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._deconfigure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="deconfigure_wan_circuits",
            predicate=self._is_isp_circuit,
            interfaces_log_label="WAN ISP circuit interfaces",
        )

    # ------------------------------------------------------------------
    # Direct-peer interface operations
    # ------------------------------------------------------------------

    def configure_direct_peer_interfaces(self, config_yaml_file: str) -> dict:
        """
        Configure direct-peer interfaces for multiple devices concurrently.

        Pushes direct-peer (`circuit: direct-peer-*`) interfaces.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._configure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="configure_direct_peer_interfaces",
            predicate=self._is_direct_peer,
            interfaces_log_label="direct-peer interfaces",
        )

    def deconfigure_direct_peer_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deconfigure direct-peer interfaces for multiple devices concurrently (idempotent).

        Resets direct-peer interfaces to the enterprise default LAN. Checks current
        device state via `gsdk.get_device_info` and skips interfaces that do not
        exist on the device -- safe to run multiple times.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self._deconfigure_interfaces_by_predicate(
            config_yaml_file=config_yaml_file,
            operation_name="deconfigure_direct_peer_interfaces",
            predicate=self._is_direct_peer,
            interfaces_log_label="direct-peer interfaces",
        )

    # ------------------------------------------------------------------
    # Syslog target operations
    # ------------------------------------------------------------------

    def configure_syslog_targets(self, config_yaml_file: str) -> dict:
        """
        Configure per-VRF syslog targets for multiple devices concurrently.

        Pushes `core.vrfs.<vrf>.syslogTargets` blocks. Each declared target is sent
        as `{"target": {...}}`; the wrapper must remain an object per the
        Core SDK/backend spec.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            output_config: Dict[int, Dict[str, Any]] = {}

            if "backbone_devices" not in config_data:
                LOG.warning("No backbone_devices configuration found in %s", config_yaml_file)
                return result

            for device_name, core_block in self._iter_backbone_devices(config_data):
                try:
                    vrfs_block = self._build_vrfs_syslog_block(core_block)
                    if not vrfs_block:
                        LOG.info(" ✗ Skipping device '%s' - no vrfs/syslogTargets found", device_name)
                        continue

                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[configure_syslog_targets] Processing device: %s (ID: %s)", device_name, device_id)

                    targets_total = sum(len(v.get("syslogTargets", {})) for v in vrfs_block.get("vrfs", {}).values())
                    output_config[device_id] = {"device_id": device_id, "core": vrfs_block}
                    LOG.info(
                        " ✓ To configure %s syslog target(s) across %s VRF(s) for device: %s",
                        targets_total,
                        len(vrfs_block.get("vrfs", {})),
                        device_name,
                    )

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring syslog targets for device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Syslog target configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["configured_devices"] = list(output_config.keys())
                LOG.info("Successfully configured backbone syslog targets for %s devices", len(output_config))
            else:
                LOG.warning("No backbone syslog target configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in backbone syslog target configuration: %s", str(e))
            raise ConfigurationError(f"Backbone syslog target configuration failed: {str(e)}")

    def deconfigure_syslog_targets(self, config_yaml_file: str) -> dict:
        """
        Deconfigure per-VRF syslog targets for multiple devices concurrently (idempotent).

        Removes `core.vrfs.<vrf>.syslogTargets` blocks by setting each entry's inner
        `target` to `null` (the wrapper must remain an object per the
        Core SDK/backend spec).

        Checks current device state via `gsdk.get_device_info` and skips targets that
        do not exist on the device -- otherwise the backend returns an error for missing
        targets. Mirrors the existence-check pattern in
        `deconfigure_core_to_core_interfaces` -- safe to run multiple times.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped targets

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "skipped_targets": [],
        }

        try:
            config_data = self.render_config_file(config_yaml_file)
            output_config: Dict[int, Dict[str, Any]] = {}

            if "backbone_devices" not in config_data:
                LOG.warning("No backbone_devices configuration found in %s", config_yaml_file)
                return result

            for device_name, core_block in self._iter_backbone_devices(config_data):
                try:
                    vrfs_in = core_block.get("vrfs") or {}
                    if not isinstance(vrfs_in, dict) or not vrfs_in:
                        LOG.info(" ✗ Skipping device '%s' - no vrfs/syslogTargets found", device_name)
                        continue

                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[deconfigure_backbone_targets] Processing device: %s (ID: %s)", device_name, device_id)

                    # Idempotency check: fetch current device state to see which targets actually exist.
                    try:
                        gcs_device_info = self.gsdk.get_device_info(device_id)
                    except Exception as exc:  # pylint: disable=broad-except
                        LOG.warning(
                            "get_device_info failed for %s (%s); proceeding without existence check: %s",
                            device_name,
                            device_id,
                            exc,
                        )
                        gcs_device_info = None

                    existing_by_vrf = self._get_existing_syslog_targets(gcs_device_info)

                    vrfs_payload: Dict[str, Any] = {}
                    targets_to_deconfigure = 0
                    for vrf_name, vrf_cfg in vrfs_in.items():
                        if not isinstance(vrf_cfg, dict):
                            continue
                        targets = vrf_cfg.get("syslogTargets") or vrf_cfg.get("syslog_targets") or {}
                        # Normalize list-of-{name,target} shape to a dict keyed by name (value unused below).
                        if isinstance(targets, list):
                            targets = {
                                item["name"]: None for item in targets if isinstance(item, dict) and item.get("name")
                            }
                        if not isinstance(targets, dict) or not targets:
                            continue
                        existing_names = existing_by_vrf.get(vrf_name)
                        kept: Dict[str, Any] = {}
                        for target_name in targets:
                            target_exists = gcs_device_info is None or (
                                existing_names and target_name in existing_names
                            )
                            if target_exists:
                                kept[target_name] = {"target": None}
                                LOG.info(
                                    " ✓ Syslog target '%s' exists in VRF '%s' on %s, will deconfigure",
                                    target_name,
                                    vrf_name,
                                    device_name,
                                )
                            else:
                                LOG.info(
                                    " ✗ Syslog target '%s' does not exist in VRF '%s' on %s, skipping",
                                    target_name,
                                    vrf_name,
                                    device_name,
                                )
                                result["skipped_targets"].append(
                                    {
                                        "device": device_name,
                                        "vrf": vrf_name,
                                        "target": target_name,
                                        "reason": "Syslog target does not exist",
                                    }
                                )
                        if kept:
                            vrfs_payload[vrf_name] = {"syslogTargets": kept}
                            targets_to_deconfigure += len(kept)

                    if not vrfs_payload:
                        LOG.info("Device %s: All syslog targets already deconfigured or not configured", device_name)
                        continue

                    output_config[device_id] = {"device_id": device_id, "core": {"vrfs": vrfs_payload}}
                    LOG.info(
                        "Device %s summary: %s syslog target(s) across %s VRF(s) to be deconfigured",
                        device_name,
                        targets_to_deconfigure,
                        len(vrfs_payload),
                    )

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring syslog targets for device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Syslog target deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info("Successfully deconfigured backbone syslog targets for %s devices", len(output_config))
            else:
                LOG.info("No backbone syslog targets to deconfigure (all already absent or unconfigured)")

            return result

        except Exception as e:
            LOG.error("Error in backbone syslog target deconfiguration: %s", str(e))
            raise ConfigurationError(f"Backbone syslog target deconfiguration failed: {str(e)}")

    # ------------------------------------------------------------------
    # Internal: predicate-based configure / deconfigure drivers
    # ------------------------------------------------------------------

    def _configure_interfaces_by_predicate(
        self,
        config_yaml_file: str,
        operation_name: str,
        predicate,
        interfaces_log_label: str,
    ) -> dict:
        """
        Generic per-device configure driver shared by interface-type-filtered ops.

        Iterates the rendered config, filters interfaces by `predicate`, renders
        them via the backbone template with `action="add"`, and pushes a single
        per-device payload concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations
            operation_name: Name of the calling public operation (used in log prefix).
            predicate: Function called with each interface_cfg dict; only entries returning
                       True are included in the push payload.
            interfaces_log_label: Human-readable label for the interface category
                                  (used in summary log lines).

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            output_config: Dict[int, Dict[str, Any]] = {}

            if "backbone_devices" not in config_data:
                LOG.warning("No backbone_devices configuration found in %s", config_yaml_file)
                return result

            for device_name, core_block in self._iter_backbone_devices(config_data):
                try:
                    interfaces = core_block.get("interfaces") or []
                    block = self._build_interfaces_block(interfaces, predicate=predicate, action="add")
                    if not block.get("interfaces"):
                        LOG.info(" ✗ Skipping device '%s' - no matching %s found", device_name, interfaces_log_label)
                        continue

                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[%s] Processing device: %s (ID: %s)", operation_name, device_name, device_id)

                    output_config[device_id] = {"device_id": device_id, "core": block}
                    interfaces_configured = len(block["interfaces"])
                    for ifname in block["interfaces"]:
                        LOG.info(" ✓ To configure %s '%s' for device: %s", interfaces_log_label, ifname, device_name)
                    LOG.info(
                        "Device %s summary: %s %s to be configured",
                        device_name,
                        interfaces_configured,
                        interfaces_log_label,
                    )
                    LOG.info("Final config for %s: %s", device_name, block)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring %s for device %s: %s", interfaces_log_label, device_name, str(e))
                    raise ConfigurationError(f"{interfaces_log_label} configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["configured_devices"] = list(output_config.keys())
                LOG.info("Successfully configured %s for %s devices", interfaces_log_label, len(output_config))
            else:
                LOG.warning("No %s configurations to apply", interfaces_log_label)

            return result

        except Exception as e:
            LOG.error("Error in %s configuration: %s", interfaces_log_label, str(e))
            raise ConfigurationError(f"{interfaces_log_label} configuration failed: {str(e)}")

    def _deconfigure_interfaces_by_predicate(
        self,
        config_yaml_file: str,
        operation_name: str,
        predicate,
        interfaces_log_label: str,
    ) -> dict:
        """
        Generic per-device deconfigure driver shared by interface-type-filtered ops.

        Iterates the rendered config, filters interfaces by `predicate`, fetches the
        live device state via `gsdk.get_device_info` and drops interfaces and VLAN
        sub-interfaces that do not exist on the device. Renders the remaining entries
        via the backbone template with `action="default_lan"` and pushes a single
        per-device payload concurrently. This makes the operation idempotent: re-running
        it after a prior deconfigure logs skips rather than producing 404s.

        Args:
            config_yaml_file: Path to the YAML file containing backbone interface configurations
            operation_name: Name of the calling public operation (used in log prefix).
            predicate: Function called with each interface_cfg dict; only entries returning
                       True are considered for deconfiguration.
            interfaces_log_label: Human-readable label for the interface category
                                  (used in summary log lines).

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and skipped interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "skipped_interfaces": [],
        }

        try:
            config_data = self.render_config_file(config_yaml_file)
            output_config: Dict[int, Dict[str, Any]] = {}

            if "backbone_devices" not in config_data:
                LOG.warning("No backbone_devices configuration found in %s", config_yaml_file)
                return result

            for device_name, core_block in self._iter_backbone_devices(config_data):
                try:
                    interfaces = core_block.get("interfaces") or []
                    matching = [cfg for cfg in interfaces if predicate(cfg)]
                    if not matching:
                        LOG.info(" ✗ Skipping device '%s' - no matching %s found", device_name, interfaces_log_label)
                        continue

                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[%s] Processing device: %s (ID: %s)", operation_name, device_name, device_id)

                    # Idempotency check: fetch current device state to see what actually exists.
                    try:
                        gcs_device_info = self.gsdk.get_device_info(device_id)
                    except Exception as exc:  # pylint: disable=broad-except
                        LOG.warning(
                            "get_device_info failed for %s (%s); proceeding without existence check: %s",
                            device_name,
                            device_id,
                            exc,
                        )
                        gcs_device_info = None

                    # Filter interfaces and sub-interfaces by what exists on the device.
                    reset_interfaces: List[Dict[str, Any]] = []
                    for cfg in matching:
                        iname = cfg.get("name")
                        if gcs_device_info is not None and not InterfaceManager._check_interface_exists(
                            gcs_device_info, iname
                        ):
                            LOG.info(" ✗ Interface '%s' does not exist on %s, skipping", iname, device_name)
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": iname,
                                    "vlan": None,
                                    "reason": "Interface does not exist",
                                }
                            )
                            continue

                        if "loopback" in iname.lower():
                            LOG.info(" ✗ Skipping loopback interface '%s' for device %s", iname, device_name)
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": iname,
                                    "vlan": None,
                                    "reason": "Loopback interface",
                                }
                            )
                            continue

                        reset_cfg = copy.deepcopy(cfg)
                        declared_subs = reset_cfg.get("subinterfaces") or reset_cfg.get("sub_interfaces") or []
                        if declared_subs and gcs_device_info is not None:
                            existing_subs: List[Dict[str, Any]] = []
                            for sub in declared_subs:
                                vlan = sub.get("vlan") or sub.get("vlan_id") or sub.get("vlanId")
                                if vlan is not None and InterfaceManager._check_interface_exists(
                                    gcs_device_info, iname, vlan
                                ):
                                    existing_subs.append(sub)
                                    LOG.info(
                                        " ✓ Subinterface '%s.%s' exists on %s, will deconfigure",
                                        iname,
                                        vlan,
                                        device_name,
                                    )
                                else:
                                    LOG.info(
                                        " ✗ Subinterface '%s.%s' does not exist on %s, skipping",
                                        iname,
                                        vlan,
                                        device_name,
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": iname,
                                            "vlan": vlan,
                                            "reason": "Subinterface does not exist",
                                        }
                                    )
                            if existing_subs:
                                reset_cfg["subinterfaces"] = existing_subs
                            else:
                                reset_cfg.pop("subinterfaces", None)
                                reset_cfg.pop("sub_interfaces", None)

                        LOG.info(
                            " ✓ Interface '%s' exists on %s, will reset to default LAN",
                            iname,
                            device_name,
                        )
                        reset_interfaces.append(reset_cfg)

                    if not reset_interfaces:
                        LOG.info(
                            "Device %s: All %s already deconfigured or not configured",
                            device_name,
                            interfaces_log_label,
                        )
                        continue

                    block = self._build_interfaces_block(reset_interfaces, predicate=None, action="default_lan")
                    if not block.get("interfaces"):
                        LOG.info(
                            "Device %s: No %s payloads to apply after existence check",
                            device_name,
                            interfaces_log_label,
                        )
                        continue

                    output_config[device_id] = {"device_id": device_id, "core": block}
                    LOG.info(
                        "Device %s summary: %s %s to be deconfigured",
                        device_name,
                        len(block["interfaces"]),
                        interfaces_log_label,
                    )
                    LOG.info("Final config for %s: %s", device_name, block)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring %s for device %s: %s", interfaces_log_label, device_name, str(e))
                    raise ConfigurationError(
                        f"{interfaces_log_label} deconfiguration failed for {device_name}: {str(e)}"
                    )

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info("Successfully deconfigured %s for %s devices", interfaces_log_label, len(output_config))
            else:
                LOG.info("No %s to deconfigure (all already absent or unconfigured)", interfaces_log_label)

            return result

        except Exception as e:
            LOG.error("Error in %s deconfiguration: %s", interfaces_log_label, str(e))
            raise ConfigurationError(f"{interfaces_log_label} deconfiguration failed: {str(e)}")
