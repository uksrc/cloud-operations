"""
Global Configuration Manager for Graphiant Playbooks.

Manages prefix sets, routing policies (BGP filters), SNMP, syslog, NTP, IPFIX, VPN profiles,
LAN segments, and site lists. Deconfigure operations are idempotent.

Result lists are mutually exclusive:
- skipped: objects that do not exist on the portal.
- failed_objects: objects that exist but are in use (cannot be deleted).
result['failed'] is True when any object is in failed_objects; the Ansible task then
fails with deleted/skipped/failed_objects reported.
"""

from typing import Dict, Any, List, Tuple

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()


class GlobalConfigManager(BaseManager):
    """
    Manages global configuration objects.

    Handles the configuration and deconfiguration of global objects
    such as prefix sets, routing policies, and system services.
    """

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure global objects based on the provided YAML file.

        This method handles the configuration of all global objects including:
        - Prefix sets (global_prefix_sets)
        - BGP filters (routing_policies)
        - SNMP global objects (snmps)
        - Syslog global objects (syslog_servers)
        - NTP global objects (ntps)
        - IPFIX global objects (ipfix_exporters)
        - VPN profile global objects (vpn_profiles)
        - LAN segments (lan_segments)
        - Site lists (site_lists)

        Args:
            config_yaml_file: Path to the YAML file containing global configurations

        Returns:
            dict: Result with 'changed' (bool), 'failed' (bool), and 'details' (per-object-type
                  sub-results, each with at least 'changed' and optionally 'failed').

        Raises:
            ConfigurationError: If configuration processing fails
        """
        result: Dict[str, Any] = {"changed": False, "failed": False, "details": {}}

        try:
            config_data = self.render_config_file(config_yaml_file)

            # Configure prefix sets (no idempotency check - assume changed if present)
            if "global_prefix_sets" in config_data:
                sub = self.configure_prefix_sets(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["prefix_sets"] = sub

            # Configure routing policies (BGP filters) (no idempotency check - assume changed)
            if "routing_policies" in config_data:
                sub = self.configure_bgp_filters(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["routing_policies"] = sub

            # Configure Graphiant routing policies (GraphiantIn/GraphiantOut filters)
            if "graphiant_routing_policies" in config_data:
                sub = self.configure_graphiant_filters(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["graphiant_routing_policies"] = sub

            # Configure SNMP global objects (no idempotency check - assume changed if present)
            if "snmps" in config_data:
                sub = self.configure_snmp_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["snmps"] = sub

            # Configure syslog global objects (no idempotency check - assume changed if present)
            if "syslog_servers" in config_data:
                sub = self.configure_syslog_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["syslog_servers"] = sub

            # Configure NTP global objects (no idempotency check - assume changed if present)
            if "ntps" in config_data:
                sub = self.configure_ntps(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["ntps"] = sub

            # Configure IPFIX global objects (no idempotency check - assume changed if present)
            if "ipfix_exporters" in config_data:
                sub = self.configure_ipfix_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["ipfix_exporters"] = sub

            # Configure VPN profiles (no idempotency check - assume changed if present)
            if "vpn_profiles" in config_data:
                sub = self.configure_vpn_profiles(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["vpn_profiles"] = sub

            # Configure LAN segments (has idempotency check)
            if "lan_segments" in config_data:
                sub = self.configure_lan_segments(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["lan_segments"] = sub

            # Configure site lists (has idempotency check)
            if "site_lists" in config_data:
                sub = self.configure_site_lists(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["site_lists"] = sub

            return result

        except Exception as e:
            LOG.error("Error in global configuration: %s", str(e))
            raise ConfigurationError(f"Global configuration failed: {str(e)}")

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure global objects based on the provided YAML file.

        This method handles the deconfiguration of all global objects including:
        - Prefix sets (global_prefix_sets)
        - BGP filters (routing_policies)
        - SNMP global objects (snmps)
        - Syslog global objects (syslog_servers)
        - NTP global objects (ntps)
        - IPFIX global objects (ipfix_exporters)
        - VPN profile global objects (vpn_profiles)
        - LAN segments (lan_segments)
        - Site lists (site_lists)

        Args:
            config_yaml_file: Path to the YAML file containing global configurations

        Returns:
            dict: Result with 'changed', 'failed' (bool), and 'details' per object type.

        Raises:
            ConfigurationError: If configuration processing fails
        """
        result: Dict[str, Any] = {"changed": False, "failed": False, "details": {}}

        try:
            config_data = self.render_config_file(config_yaml_file)

            # Deconfigure prefix sets (idempotent; changed only if something was removed)
            if "global_prefix_sets" in config_data:
                sub = self.deconfigure_prefix_sets(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["prefix_sets"] = sub

            # Deconfigure routing policies / BGP filters (idempotent; check existence then single payload)
            if "routing_policies" in config_data:
                sub = self.deconfigure_bgp_filters(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["routing_policies"] = sub

            # Deconfigure Graphiant routing policies (idempotent)
            if "graphiant_routing_policies" in config_data:
                sub = self.deconfigure_graphiant_filters(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["graphiant_routing_policies"] = sub

            # Deconfigure SNMP global objects (idempotent; changed only if something was removed)
            if "snmps" in config_data:
                sub = self.deconfigure_snmp_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["snmps"] = sub

            # Deconfigure syslog global objects (idempotent; changed only if something was removed)
            if "syslog_servers" in config_data:
                sub = self.deconfigure_syslog_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["syslog_servers"] = sub

            # Deconfigure NTP global objects (idempotent; changed only if something was removed)
            if "ntps" in config_data:
                sub = self.deconfigure_ntps(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["ntps"] = sub

            # Deconfigure IPFIX global objects (idempotent; changed only if something was removed)
            if "ipfix_exporters" in config_data:
                sub = self.deconfigure_ipfix_services(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["ipfix_exporters"] = sub

            # Deconfigure VPN profile global objects (idempotent; check existence then single payload)
            if "vpn_profiles" in config_data:
                sub = self.deconfigure_vpn_profiles(config_yaml_file)
                if sub.get("changed"):
                    result["changed"] = True
                if sub.get("failed"):
                    result["failed"] = True
                result["details"]["vpn_profiles"] = sub

            # Deconfigure LAN segments (has idempotency check)
            if "lan_segments" in config_data:
                lan_result = self.deconfigure_lan_segments(config_yaml_file)
                if lan_result.get("changed"):
                    result["changed"] = True
                if lan_result.get("failed"):
                    result["failed"] = True
                result["details"]["lan_segments"] = lan_result

            # Deconfigure site lists (has idempotency check)
            if "site_lists" in config_data:
                site_list_result = self.deconfigure_site_lists(config_yaml_file)
                if site_list_result.get("changed"):
                    result["changed"] = True
                if site_list_result.get("failed"):
                    result["failed"] = True
                result["details"]["site_lists"] = site_list_result

            return result

        except Exception as e:
            LOG.error("Error in global deconfiguration: %s", str(e))
            raise ConfigurationError(f"Global deconfiguration failed: {str(e)}")

    def configure_prefix_sets(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global prefix sets.

        Args:
            config_yaml_file: Path to the YAML file containing prefix set configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            prefix_sets = config_data.get("global_prefix_sets", [])

            if not prefix_sets:
                LOG.info("No prefix sets found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"global_prefix_sets": {}}

            for prefix_config in prefix_sets:
                self.config_utils.global_prefix_set(config_payload, action="add", **prefix_config)

            LOG.info("Configure prefix sets payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s prefix sets", len(prefix_sets))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure prefix sets: %s", e)
            raise ConfigurationError(f"Prefix sets configuration failed: {e}")

    def deconfigure_prefix_sets(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global prefix sets (idempotent).

        Fetches summaries from the portal; objects with num_attached_devices,
        num_attached_sites, or num_policies > 0 cannot be deleted and are marked
        as failed. Deletes existing, unattached objects one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            prefix_sets = config_data.get("global_prefix_sets", [])

            if not prefix_sets:
                LOG.info("No prefix sets found in configuration file")
                return result

            names = [p.get("name", "unknown") for p in prefix_sets]
            LOG.info("Attempting to deconfigure prefix sets: %s", names)

            summaries = self.gsdk.get_global_prefix_set_summaries()
            LOG.info("Prefix set summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=True)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                prefix_sets, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for prefix sets; "
                    "assuming no prefix sets exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "Prefix set(s) in use (num_attached_devices, num_attached_sites, "
                    "or num_policies > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "Prefix sets do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [p.get("name", "unknown") for p in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for prefix_config in to_delete:
                name = prefix_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"global_prefix_sets": {}}
                self.config_utils.global_prefix_set(single_payload, action="delete", **prefix_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("Prefix set '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"Prefix sets deconfiguration failed: {e}") from e
            LOG.info(
                "Prefix sets deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure prefix sets: %s", e)
            raise ConfigurationError(f"Prefix sets deconfiguration failed: {e}")

    def configure_bgp_filters(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global BGP filters.

        Args:
            config_yaml_file: Path to the YAML file containing BGP filter configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            routing_policies = config_data.get("routing_policies", [])

            if not routing_policies:
                LOG.info("No BGP filters found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"routing_policies": {}}

            for policy_config in routing_policies:
                self.config_utils.global_bgp_filter(config_payload, action="add", **policy_config)

            LOG.info("Configure BGP filters payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s BGP filters", len(routing_policies))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure BGP filters: %s", e)
            raise ConfigurationError(f"BGP filters configuration failed: {e}")

    def deconfigure_bgp_filters(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global BGP filters (idempotent).

        Fetches summaries from the portal; filters with num_attached_devices or
        num_attached_sites > 0 cannot be deleted and are marked as failed. Deletes
        existing, unattached filters one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            routing_policies = config_data.get("routing_policies", [])

            if not routing_policies:
                LOG.info("No BGP filters found in configuration file")
                return result

            names = [p.get("name", "unknown") for p in routing_policies]
            LOG.info("Attempting to deconfigure BGP filters: %s", names)

            summaries = self.gsdk.get_global_routing_policy_summaries()
            LOG.info("BGP filter summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                routing_policies, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for BGP filters; "
                    "assuming no BGP filters exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "BGP filter(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "BGP filters do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [p.get("name", "unknown") for p in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for policy_config in to_delete:
                name = policy_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"routing_policies": {}}
                self.config_utils.global_bgp_filter(single_payload, action="delete", **policy_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("BGP filter '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"BGP filters deconfiguration failed: {e}") from e
            LOG.info(
                "BGP filters deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure BGP filters: %s", e)
            raise ConfigurationError(f"BGP filters deconfiguration failed: {e}")

    def configure_graphiant_filters(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global Graphiant filters (attachPoint GraphiantIn / GraphiantOut).

        Args:
            config_yaml_file: Path to the YAML file containing Graphiant filter configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            graphiant_policies = config_data.get("graphiant_routing_policies", [])

            if not graphiant_policies:
                LOG.info("No Graphiant filters found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"routing_policies": {}}

            for policy_config in graphiant_policies:
                self.config_utils.global_graphiant_filter(config_payload, action="add", **policy_config)

            LOG.info("Configure Graphiant filters payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s Graphiant filters", len(graphiant_policies))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure Graphiant filters: %s", e)
            raise ConfigurationError(f"Graphiant filters configuration failed: {e}")

    def deconfigure_graphiant_filters(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global Graphiant filters (idempotent).

        Uses same routing policy summary as BGP; deletes existing, unattached policies one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            graphiant_policies = config_data.get("graphiant_routing_policies", [])

            if not graphiant_policies:
                LOG.info("No Graphiant filters found in configuration file")
                return result

            names = [p.get("name", "unknown") for p in graphiant_policies]
            LOG.info("Attempting to deconfigure Graphiant filters: %s", names)

            summaries = self.gsdk.get_global_routing_policy_summaries()
            LOG.info("Graphiant filter summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                graphiant_policies, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            if not summaries:
                LOG.info(
                    "Summary API returned empty for Graphiant filters; "
                    "assuming no Graphiant filters exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "Graphiant filter(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "Graphiant filters do not exist, nothing to deconfigure (idempotent). "
                    "skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [p.get("name", "unknown") for p in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for policy_config in to_delete:
                name = policy_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"routing_policies": {}}
                self.config_utils.global_graphiant_filter(single_payload, action="delete", **policy_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("Graphiant filter '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"Graphiant filters deconfiguration failed: {e}") from e
            LOG.info(
                "Graphiant filters deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure Graphiant filters: %s", e)
            raise ConfigurationError(f"Graphiant filters deconfiguration failed: {e}")

    def configure_snmp_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global SNMP services.

        Args:
            config_yaml_file: Path to the YAML file containing SNMP service configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            snmp_services = config_data.get("snmps", [])

            if not snmp_services:
                LOG.info("No SNMP services found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"snmps": {}}

            for snmp_config in snmp_services:
                self.config_utils.global_snmp(config_payload, action="add", **snmp_config)

            LOG.debug("Configure SNMP services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s SNMP global objects", len(snmp_services))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure SNMP services: %s", e)
            raise ConfigurationError(f"SNMP services configuration failed: {e}")

    def deconfigure_snmp_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global SNMP services (idempotent).

        Fetches summaries from the portal; objects with numAttachedDevices > 0
        cannot be deleted and are marked as failed. Deletes existing, unattached
        objects one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            snmp_services = config_data.get("snmps", [])

            if not snmp_services:
                LOG.info("No SNMP services found in configuration file")
                return result

            names = [s.get("name", "unknown") for s in snmp_services]
            LOG.info("Attempting to deconfigure SNMP objects: %s", names)

            summaries = self.gsdk.get_global_snmp_summaries()
            LOG.info("SNMP summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                snmp_services, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for SNMP objects; "
                    "assuming no SNMP objects exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "SNMP object(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "SNMP objects do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [s.get("name", "unknown") for s in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for snmp_config in to_delete:
                name = snmp_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"snmps": {}}
                self.config_utils.global_snmp(single_payload, action="delete", **snmp_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("SNMP object '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e, ("failed querying snmp",)):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"SNMP services deconfiguration failed: {e}") from e
            LOG.info(
                "SNMP deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure SNMP services: %s", e)
            raise ConfigurationError(f"SNMP services deconfiguration failed: {e}")

    def configure_syslog_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global syslog services.

        Args:
            config_yaml_file: Path to the YAML file containing syslog service configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            syslog_services = config_data.get("syslog_servers", [])

            if not syslog_services:
                LOG.info("No syslog services found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"syslog_servers": {}}

            for syslog_config in syslog_services:
                self.config_utils.global_syslog(config_payload, action="add", **syslog_config)

            LOG.debug("Configure syslog services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s syslog global objects", len(syslog_services))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure syslog services: %s", e)
            raise ConfigurationError(f"Syslog services configuration failed: {e}")

    def deconfigure_syslog_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global syslog services (idempotent).

        Fetches summaries from the portal; objects with numAttachedDevices > 0
        cannot be deleted and are marked as failed. Deletes existing, unattached
        objects one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            syslog_services = config_data.get("syslog_servers", [])

            if not syslog_services:
                LOG.info("No syslog services found in configuration file")
                return result

            names = [s.get("name", "unknown") for s in syslog_services]
            LOG.info("Attempting to deconfigure syslog objects: %s", names)

            summaries = self.gsdk.get_global_syslog_server_summaries()
            LOG.info("Syslog server summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                syslog_services, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for syslog servers; "
                    "assuming no syslog servers exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "Syslog object(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "Syslog objects do not exist, nothing to deconfigure (idempotent). "
                    "skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [s.get("name", "unknown") for s in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for syslog_config in to_delete:
                name = syslog_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"syslog_servers": {}}
                self.config_utils.global_syslog(single_payload, action="delete", **syslog_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("Syslog object '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"Syslog services deconfiguration failed: {e}") from e
            LOG.info(
                "Syslog deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure syslog services: %s", e)
            raise ConfigurationError(f"Syslog services deconfiguration failed: {e}")

    def configure_ntps(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global NTP objects.

        Args:
            config_yaml_file: Path to the YAML file containing NTP configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            ntps = config_data.get("ntps", [])

            if not ntps:
                LOG.info("No NTP objects found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"ntps": {}}

            for ntp_config in ntps:
                self.config_utils.global_ntp(config_payload, action="add", **ntp_config)

            LOG.debug("Configure NTP payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s NTP global objects", len(ntps))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure NTP objects: %s", e)
            raise ConfigurationError(f"NTP configuration failed: {e}")

    def deconfigure_ntps(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global NTP objects (idempotent).

        Fetches summaries from the portal; objects with numAttachedDevices > 0
        cannot be deleted and are marked as failed. Deletes existing, unattached
        objects one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            ntps = config_data.get("ntps", [])

            if not ntps:
                LOG.info("No NTP objects found in configuration file")
                return result

            names = [n.get("name", "unknown") for n in ntps]
            LOG.info("Attempting to deconfigure NTP objects: %s", names)

            summaries = self.gsdk.get_global_ntp_summaries()
            LOG.info("NTP summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                ntps, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for NTP objects; "
                    "assuming no NTP objects exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "NTP object(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "NTP objects do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [n.get("name", "unknown") for n in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for ntp_config in to_delete:
                name = ntp_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"ntps": {}}
                self.config_utils.global_ntp(single_payload, action="delete", **ntp_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("NTP object '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"NTP deconfiguration failed: {e}") from e
            LOG.info(
                "NTP deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure NTP objects: %s", e)
            raise ConfigurationError(f"NTP deconfiguration failed: {e}")

    def configure_ipfix_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global IPFIX services.

        Args:
            config_yaml_file: Path to the YAML file containing IPFIX service configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            ipfix_services = config_data.get("ipfix_exporters", [])

            if not ipfix_services:
                LOG.info("No IPFIX services found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"ipfix_exporters": {}}

            for ipfix_config in ipfix_services:
                self.config_utils.global_ipfix(config_payload, action="add", **ipfix_config)

            LOG.debug("Configure IPFIX services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s IPFIX global objects", len(ipfix_services))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure IPFIX services: %s", e)
            raise ConfigurationError(f"IPFIX services configuration failed: {e}")

    def deconfigure_ipfix_services(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global IPFIX services (idempotent).

        Fetches summaries from the portal; objects with numAttachedDevices > 0
        cannot be deleted and are marked as failed. Deletes existing, unattached
        objects one by one.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            ipfix_services = config_data.get("ipfix_exporters", [])

            if not ipfix_services:
                LOG.info("No IPFIX services found in configuration file")
                return result

            names = [i.get("name", "unknown") for i in ipfix_services]
            LOG.info("Attempting to deconfigure IPFIX objects: %s", names)

            summaries = self.gsdk.get_global_ipfix_exporter_summaries()
            LOG.info("IPFIX exporter summaries: %s", summaries)

            def object_in_use(s):
                return self.gsdk.is_global_object_in_use(s, check_num_policies=False)

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                ipfix_services, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            # When summary API returned empty, assume no objects of this type exist (API fixed);
            # skipped = all requested.
            if not summaries:
                LOG.info(
                    "Summary API returned empty for IPFIX exporters; "
                    "assuming no IPFIX exporters exist (nothing to deconfigure)."
                )

            if result["failed"]:
                LOG.warning(
                    "IPFIX object(s) in use (num_attached_devices or num_attached_sites > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "IPFIX objects do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [i.get("name", "unknown") for i in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for ipfix_config in to_delete:
                name = ipfix_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"ipfix_exporters": {}}
                self.config_utils.global_ipfix(single_payload, action="delete", **ipfix_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    if _is_in_use_error(e):
                        result["failed_objects"].append(name)
                        result["failed"] = True
                        LOG.warning("IPFIX object '%s' could not be deleted (in use): %s", name, e)
                    elif _is_not_found_error(e):
                        result["skipped"].append(name)
                    else:
                        raise ConfigurationError(f"IPFIX services deconfiguration failed: {e}") from e
            LOG.info(
                "IPFIX deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure IPFIX services: %s", e)
            raise ConfigurationError(f"IPFIX services deconfiguration failed: {e}")

    def configure_vpn_profiles(self, config_yaml_file: str) -> Dict[str, Any]:
        """Configure global VPN profiles.

        Args:
            config_yaml_file: Path to the YAML file containing VPN profile configurations

        Returns:
            dict: Result with 'changed' and 'failed' (bool).
        """
        result: Dict[str, Any] = {"changed": False, "failed": False}
        try:
            config_data = self.render_config_file(config_yaml_file)
            vpn_profiles = config_data.get("vpn_profiles", [])

            if not vpn_profiles:
                LOG.info("No VPN profiles found in configuration file")
                return result

            config_payload: Dict[str, Any] = {"vpn_profiles": {}}

            for vpn_config in vpn_profiles:
                self.config_utils.global_vpn_profile(config_payload, action="add", **vpn_config)

            LOG.info("Configure VPN profiles payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s VPN profiles", len(vpn_profiles))
            result["changed"] = True
            return result
        except Exception as e:
            LOG.error("Failed to configure VPN profiles: %s", e)
            raise ConfigurationError(f"VPN profiles configuration failed: {e}")

    def deconfigure_vpn_profiles(self, config_yaml_file: str) -> Dict[str, Any]:
        """Deconfigure global VPN profiles (idempotent).

        Uses GET /v1/global/ipsec-profile response C(count): if count > 0 the profile is in use
        and is not deleted (added to failed_objects). Partition: skipped = not on portal;
        failed_objects = on portal but in use (count > 0). Only profiles not in use are deleted.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list)
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}
        try:
            config_data = self.render_config_file(config_yaml_file)
            vpn_profiles = config_data.get("vpn_profiles", [])

            if not vpn_profiles:
                LOG.info("No VPN profiles found in configuration file")
                return result

            names = [v.get("name", "unknown") for v in vpn_profiles]
            LOG.info("Attempting to deconfigure VPN profiles: %s", names)

            existing_profiles = self.gsdk.get_global_ipsec_profiles()
            # Summaries with 'name' and 'count' (count > 0 => profile in use, cannot delete)
            summaries = [
                {"name": name, "count": getattr(entry, "count", 0) or 0}
                for name, entry in (existing_profiles or {}).items()
            ]
            if not summaries:
                LOG.info(
                    "No VPN profiles exist on portal; assuming nothing to deconfigure (all requested will be skipped)."
                )

            def object_in_use(s):
                return (s.get("count", 0) if isinstance(s, dict) else getattr(s, "count", 0) or 0) > 0

            to_delete, result["skipped"], result["failed_objects"] = _partition_global_objects_for_deconfigure(
                vpn_profiles, summaries, object_in_use
            )
            result["failed"] = bool(result["failed_objects"])

            if result["failed"]:
                LOG.warning(
                    "VPN profile(s) in use (count > 0), cannot delete: %s",
                    result["failed_objects"],
                )
            if not to_delete:
                LOG.info(
                    "VPN profiles do not exist, nothing to deconfigure (idempotent). skipped=%s, failed_objects=%s",
                    result["skipped"],
                    result["failed_objects"],
                )
                return result

            LOG.info(
                "Partition: to_delete=%s, skipped=%s, failed_objects=%s",
                [v.get("name", "unknown") for v in to_delete],
                result["skipped"],
                result["failed_objects"],
            )
            for vpn_config in to_delete:
                name = vpn_config.get("name", "unknown")
                single_payload: Dict[str, Any] = {"vpn_profiles": {}}
                self.config_utils.global_vpn_profile(single_payload, action="delete", **vpn_config)
                try:
                    self.gsdk.patch_global_config(**single_payload)
                    result["deleted"].append(name)
                    result["changed"] = True
                except Exception as e:
                    result["failed_objects"].append(name)
                    result["failed"] = True
                    LOG.warning("VPN profile '%s' delete failed: %s", name, e)
            LOG.info(
                "VPN profiles deconfigure: deleted=%s; skipped=%s; failed_objects=%s",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure VPN profiles: %s", e)
            raise ConfigurationError(f"VPN profiles deconfiguration failed: {e}")

    def configure_lan_segments(self, config_yaml_file: str) -> dict:
        """Configure global LAN segments.

        Args:
            config_yaml_file: Path to the YAML file containing LAN segment configurations

        Returns:
            dict: Result with 'changed' status and lists of created/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "failed": False, "created": [], "skipped": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            lan_segments = config_data.get("lan_segments", [])

            if not lan_segments:
                LOG.info("No LAN segments found in configuration file")
                return result

            # Get existing LAN segments to check if they already exist
            existing_segments = self.gsdk.get_global_lan_segments()
            existing_names = {segment.name for segment in existing_segments}

            for segment_config in lan_segments:
                segment_name = segment_config.get("name")
                segment_description = segment_config.get("description", "")

                if segment_name in existing_names:
                    LOG.info("LAN segment '%s' already exists, skipping creation", segment_name)
                    result["skipped"].append(segment_name)
                else:
                    LOG.info("Creating LAN segment: %s", segment_name)
                    response = self.gsdk.post_global_lan_segments(name=segment_name, description=segment_description)
                    LOG.info("Successfully created LAN segment '%s' with ID: %s", segment_name, response.id)
                    result["created"].append(segment_name)
                    result["changed"] = True

            LOG.info("Successfully processed %s LAN segments (changed: %s)", len(lan_segments), result["changed"])
            return result
        except Exception as e:
            LOG.error("Failed to configure LAN segments: %s", e)
            raise ConfigurationError(f"LAN segment configuration failed: {e}")

    def deconfigure_lan_segments(self, config_yaml_file: str) -> dict:
        """Deconfigure global LAN segments (idempotent).

        Skipped = segment not on portal (no delete attempted). failed_objects = exists but in use
        (references or delete returned False). When no segments exist on portal, all requested are skipped.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list).
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            lan_segments = config_data.get("lan_segments", [])

            if not lan_segments:
                LOG.info("No LAN segments found in configuration file")
                return result

            # Get existing LAN segments to find IDs for deletion
            existing_segments = self.gsdk.get_global_lan_segments()
            segments_by_name = {segment.name: segment for segment in existing_segments}
            if not segments_by_name:
                LOG.info(
                    "No LAN segments exist on portal; assuming nothing to deconfigure (all requested will be skipped)."
                )

            names = [s.get("name") for s in lan_segments if s.get("name")]
            LOG.info("Attempting to deconfigure LAN segments: %s", names)

            for segment_config in lan_segments:
                segment_name = segment_config.get("name")

                if segment_name in segments_by_name:
                    segment = segments_by_name[segment_name]
                    refs_site = getattr(segment, "site_list_references", 0) or 0
                    refs_edge = getattr(segment, "edge_references", 0) or 0
                    refs_ifaces = getattr(segment, "associated_interfaces", 0) or 0
                    # Check if segment has any references before deletion
                    if refs_site == 0 and refs_edge == 0 and refs_ifaces == 0:
                        LOG.info("Deleting LAN segment '%s' (ID: %s) - no references found", segment_name, segment.id)
                        success = self.gsdk.delete_global_lan_segments(segment.id)
                        if success:
                            LOG.info("Successfully deleted LAN segment '%s'", segment_name)
                            result["deleted"].append(segment_name)
                            result["changed"] = True
                        else:
                            LOG.warning("LAN segment '%s' could not be deleted (in use or error)", segment_name)
                            result["failed_objects"].append(segment_name)
                            result["failed"] = True
                    else:
                        LOG.warning(
                            "LAN segment '%s' has references (in use), cannot delete: "
                            "siteListReferences=%s, edgeReferences=%s, associatedInterfaces=%s",
                            segment_name,
                            refs_site,
                            refs_edge,
                            refs_ifaces,
                        )
                        result["failed_objects"].append(segment_name)
                        result["failed"] = True
                else:
                    LOG.info("LAN segment '%s' not found, skipping deletion", segment_name)
                    result["skipped"].append(segment_name)

            LOG.info(
                "LAN segments deconfiguration completed: deleted=%s, skipped=%s, failed_objects=%s (changed: %s)",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
                result["changed"],
            )
            return result
        except Exception as e:
            LOG.error("Failed to deconfigure LAN segments: %s", e)
            raise ConfigurationError(f"LAN segment deconfiguration failed: {e}")

    def configure_site_lists(self, config_yaml_file: str) -> dict:
        """
        Configure global site lists from YAML file.

        Args:
            config_yaml_file: Path to the YAML file containing site list configurations

        Returns:
            dict: Result with 'changed' status and lists of created/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "failed": False, "created": [], "skipped": []}

        try:
            LOG.info("Configuring global site lists from %s", config_yaml_file)

            # Load and parse YAML configuration
            try:
                config_data = self.config_utils.render_config_file(config_yaml_file)
            except ConfigurationError as e:
                # Re-raise configuration errors with better context
                raise ConfigurationError(f"Configuration file error: {str(e)}")
            if not config_data or "site_lists" not in config_data:
                LOG.info("No site_lists configuration found in YAML file")
                return result

            site_lists = config_data["site_lists"]
            if not isinstance(site_lists, list):
                raise ConfigurationError(
                    "Configuration error: 'site_lists' must be a list. Please check your YAML file structure."
                )

            for site_list_config in site_lists:
                site_list_name = site_list_config.get("name")
                if not site_list_name:
                    raise ConfigurationError(
                        "Configuration error: Each site list must have a 'name' field. "
                        "Please check your YAML file structure."
                    )

                # Check if site list already exists
                existing_site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if existing_site_list_id:
                    LOG.info(
                        "Site list '%s' already exists (ID: %s), skipping creation",
                        site_list_name,
                        existing_site_list_id,
                    )
                    result["skipped"].append(site_list_name)
                    continue

                # Get site IDs for the sites in the site list
                site_names = site_list_config.get("sites", [])
                site_ids = []

                for site_name in site_names:
                    site_id = self.gsdk.get_site_id(site_name)
                    if site_id:
                        site_ids.append(site_id)
                        LOG.info("Added site '%s' (ID: %s) to site list '%s'", site_name, site_id, site_list_name)
                    else:
                        raise ConfigurationError(
                            f"Site '{site_name}' not found for site list '{site_list_name}'. "
                            "Please ensure all sites exist before creating site lists."
                        )

                if not site_ids:
                    LOG.warning("No valid sites found for site list '%s', skipping creation", site_list_name)
                    result["skipped"].append(site_list_name)
                    continue

                # Use template approach for consistency with other global config methods
                config_payload: Dict[str, Any] = {"site_lists": {}}
                self.config_utils.global_site_list(
                    config_payload,
                    action="add",
                    name=site_list_name,
                    description=site_list_config.get("description", ""),
                    site_ids=site_ids,
                )

                # Create the site list using the generated payload
                site_list_payload = config_payload["site_lists"][site_list_name]
                self.gsdk.create_global_site_list(site_list_payload)
                LOG.info("Successfully created site list '%s'", site_list_name)
                result["created"].append(site_list_name)
                result["changed"] = True

            LOG.info(
                "Site lists configuration completed: %s created, %s skipped (changed: %s)",
                len(result["created"]),
                len(result["skipped"]),
                result["changed"],
            )
            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to configure site lists: %s", e)
            raise ConfigurationError(f"Site list configuration failed: {e}")

    def deconfigure_site_lists(self, config_yaml_file: str) -> dict:
        """
        Deconfigure global site lists from YAML file (idempotent).

        Skipped = site list not found on portal (no delete attempted). failed_objects = exists but
        in use (references). Site lists with references (site_list, edge, or policy) cannot be
        deleted and are added to result['failed_objects']; result['failed'] is True when any could not be deleted.

        Returns:
            dict: Result with 'changed', 'deleted', 'skipped', 'failed' (bool), and 'failed_objects' (list).
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "failed": False, "failed_objects": []}

        try:
            LOG.info("Deconfiguring global site lists from %s", config_yaml_file)

            # Load and parse YAML configuration
            config_data = self.config_utils.render_config_file(config_yaml_file)
            if not config_data or "site_lists" not in config_data:
                LOG.info("No site_lists configuration found in YAML file")
                return result

            site_lists = config_data["site_lists"]
            if not isinstance(site_lists, list):
                raise ConfigurationError(
                    "Configuration error: 'site_lists' must be a list. Please check your YAML file structure."
                )

            names = [s.get("name") for s in site_lists if s.get("name")]
            LOG.info("Attempting to deconfigure site lists: %s", names)

            for site_list_config in site_lists:
                site_list_name = site_list_config.get("name")
                if not site_list_name:
                    raise ConfigurationError(
                        "Configuration error: Each site list must have a 'name' field. "
                        "Please check your YAML file structure."
                    )

                # Check if site list exists
                site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if not site_list_id:
                    LOG.info("Site list '%s' not found, skipping deletion", site_list_name)
                    result["skipped"].append(site_list_name)
                    continue

                # Check if site list is in use (consistent with other global config deconfigures)
                site_list_details = self.gsdk.get_global_site_list(site_list_id)
                refs_site = getattr(site_list_details, "site_list_references", 0) or 0
                refs_edge = getattr(site_list_details, "edge_references", 0) or 0
                refs_policy = getattr(site_list_details, "policy_references", 0) or 0
                if refs_site > 0 or refs_edge > 0 or refs_policy > 0:
                    LOG.warning(
                        "Site list '%s' has references (in use), cannot delete: "
                        "siteListReferences=%s, edgeReferences=%s, policyReferences=%s",
                        site_list_name,
                        refs_site,
                        refs_edge,
                        refs_policy,
                    )
                    result["failed_objects"].append(site_list_name)
                    result["failed"] = True
                    continue

                # Delete the site list
                self.gsdk.delete_global_site_list(site_list_id)
                LOG.info("Successfully deleted site list '%s' (ID: %s)", site_list_name, site_list_id)
                result["deleted"].append(site_list_name)
                result["changed"] = True

            LOG.info(
                "Site lists deconfiguration completed: deleted=%s, skipped=%s, failed_objects=%s (changed: %s)",
                result["deleted"],
                result["skipped"],
                result["failed_objects"],
                result["changed"],
            )
            return result
        except ConfigurationError:
            # Re-raise configuration errors (reference issues, SDK errors)
            raise
        except Exception as e:
            LOG.error("Unexpected error during site list deconfiguration: %s", e)
            raise ConfigurationError(f"Site list deconfiguration failed: {e}")


def _summary_name(summary) -> str:
    """Get name from a summary dict or object; supports 'name' and 'Name'."""
    if isinstance(summary, dict):
        return summary.get("name") or summary.get("Name") or ""
    return getattr(summary, "name", None) or getattr(summary, "Name", None) or ""


def _partition_global_objects_for_deconfigure(
    config_items: List[Dict],
    summaries: List[Dict],
    object_in_use_check,
    name_key: str = "name",
) -> Tuple[List[Dict], List[str], List[str]]:
    """
    Partition requested config items into: to_delete, skipped (not on portal), failed (in use).
    object_in_use_check(summary) returns True if the object cannot be deleted (e.g. attached to devices).
    """
    summary_by_name = {}
    for s in summaries:
        n = _summary_name(s)
        if n:
            summary_by_name[n] = s
    to_delete = []
    skipped = []
    failed = []
    for item in config_items:
        name = item.get(name_key, "unknown")
        summary = summary_by_name.get(name)
        if not summary:
            skipped.append(name)
        elif object_in_use_check(summary):
            failed.append(name)
        else:
            to_delete.append(item)
    return to_delete, skipped, failed


def _is_in_use_error(exc: Exception) -> bool:
    """True if the exception indicates the object exists but is in use (cannot delete)."""
    err = str(exc).lower()
    return any(
        phrase in err
        for phrase in (
            "in use",
            "attached",
            "referenced",
            "cannot delete",
            "configured on",
            "numattached",
            "numpolic",
        )
    )


def _is_not_found_error(exc: Exception, extra_phrases: Tuple[str, ...] = ()) -> bool:
    """True if the exception indicates the object does not exist."""
    err = str(exc).lower()
    if "not exist" in err or "not found" in err:
        return True
    return any(p in err for p in extra_phrases)
