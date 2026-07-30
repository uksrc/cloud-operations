"""
Site Manager for Graphiant Playbooks.

This module handles site management operations including
attachment and detachment of global system objects to/from sites.

Deconfigure workflow consistency (with global_config_manager, interface_manager):
- Idempotency: Delete only removes sites that exist (_delete_site_if_exists); detach
  skips when site not found or object already detached. Safe to run multiple times.
- Result shape: _manage_sites returns changed, created/deleted, skipped; _manage_site_objects
  returns changed, attached/detached, skipped. No 'failed' list (errors raise).
- Logging: "Attempting to delete/detach ..." with target names, then "Deconfigure completed: ..."
  with explicit lists (aligned with global_config and interface_manager).
"""

from typing import Any, Dict, Optional, Union, cast
from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, SiteNotFoundError, ValidationError

LOG = setup_logger()


class SiteManager(BaseManager):
    """
    Manages site operations and global object attachments.

    Handles the attachment and detachment of global system objects
    (SNMP, Syslog, IPFIX, VPN profiles) to/from specific sites.
    """

    def configure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Configure sites: create sites and attach global system objects.

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        # Step 1: Create sites if they don't exist
        sites_result = self._manage_sites(config_yaml_file, operation="create")

        # Step 2: Attach global objects to sites
        objects_result = self._manage_site_objects(config_yaml_file, operation="attach")

        # Combine results
        changed = sites_result.get("changed", False) or objects_result.get("changed", False)
        return {"changed": changed, "sites": sites_result, "objects": objects_result}

    def deconfigure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Deconfigure sites: detach global system objects and delete sites.

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        # Step 1: Detach global objects from sites
        objects_result = self._manage_site_objects(config_yaml_file, operation="detach")

        # Step 2: Delete sites
        sites_result = self._manage_sites(config_yaml_file, operation="delete")

        # Combine results
        changed = sites_result.get("changed", False) or objects_result.get("changed", False)
        return {"changed": changed, "sites": sites_result, "objects": objects_result}

    def configure_sites(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Create sites (idempotent - only creates if site doesn't exist).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        return self._manage_sites(config_yaml_file, operation="create")

    def deconfigure_sites(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Delete sites (idempotent - only deletes if site exists).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        return self._manage_sites(config_yaml_file, operation="delete")

    def _manage_sites(self, config_yaml_file: str, operation: str) -> Dict[str, Any]:
        """
        Manage sites (create or delete).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations
            operation: Operation to perform - "create" or "delete"

        Returns:
            dict: Result with 'changed' status and lists of created/deleted/skipped items

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        result: Dict[str, Any] = {"changed": False, "created": [], "deleted": [], "skipped": []}

        try:
            config_data = self.render_config_file(config_yaml_file)

            if "sites" not in config_data:
                LOG.info("No sites configuration found in %s, skipping site %s", config_yaml_file, operation)
                return result

            site_names = [s.get("name") for s in (config_data.get("sites") or []) if s.get("name")]
            if operation == "delete":
                LOG.info("Attempting to delete sites: %s", site_names)
            elif operation == "create":
                LOG.info("Attempting to create sites: %s", site_names)

            for site_config in config_data.get("sites") or []:
                try:
                    site_name = site_config.get("name")
                    if not site_name:
                        raise ValidationError("Site configuration must include 'name' field")

                    if operation == "create":
                        was_created = self._create_site_if_not_exists(site_config)
                        if was_created:
                            result["created"].append(site_name)
                            result["changed"] = True
                        else:
                            result["skipped"].append(site_name)
                    elif operation == "delete":
                        was_deleted = self._delete_site_if_exists(site_name)
                        if was_deleted:
                            result["deleted"].append(site_name)
                            result["changed"] = True
                        else:
                            result["skipped"].append(site_name)

                    LOG.info("Successfully processed site: %s (operation: %s)", site_name, operation)

                except Exception as e:
                    LOG.error("Error %sing site '%s': %s", operation, site_name, str(e))
                    raise ConfigurationError(f"Failed to {operation} site {site_name}: {str(e)}")

            total_processed = len(result["created"]) + len(result["deleted"]) + len(result["skipped"])
            LOG.info("Processed %s sites (operation: %s, changed: %s)", total_processed, operation, result["changed"])
            # Explicit lists for consistency with global_config/interface_manager deconfigure logging
            if operation == "delete":
                LOG.info("Deconfigure completed: deleted=%s, skipped=%s", result["deleted"], result["skipped"])
            elif operation == "create":
                LOG.info("Configure completed: created=%s, skipped=%s", result["created"], result["skipped"])

            return result

        except Exception as e:
            LOG.error("Error in site %s operation: %s", operation, str(e))
            raise ConfigurationError(f"Site {operation} operation failed: {str(e)}")

    def _create_site_if_not_exists(self, site_config: dict) -> bool:
        """
        Create a site if it doesn't already exist (idempotent).

        Args:
            site_config: Site configuration dictionary

        Returns:
            bool: True if site was created, False if it already existed

        Raises:
            ConfigurationError: If site creation fails
        """
        site_name = site_config.get("name")

        # Check if site already exists using v1/sites/details
        if self.gsdk.site_exists(site_name):
            existing_site_id = self.gsdk.get_site_id(site_name)
            LOG.info("Site '%s' already exists with ID: %s, skipping creation", site_name, existing_site_id)
            return False

        try:
            # Prepare site data for creation (simple site creation only)
            site_data = {"site": {"name": site_name, "location": site_config.get("location", {})}}

            # Create the site
            created_site = self.gsdk.create_site(site_data)
            LOG.info("Successfully created site '%s' with ID: %s", site_name, created_site.id)
            return True

        except Exception as e:
            error_msg = str(e)
            # Handle "already exists" errors gracefully
            if "already exists" in error_msg.lower() or "already created" in error_msg.lower():
                LOG.info("Site '%s' already exists, skipping creation: %s", site_name, error_msg)
                return False
            else:
                LOG.error("Failed to create site '%s': %s", site_name, error_msg)
                raise ConfigurationError(f"Site creation failed for {site_name}: {error_msg}")

    def _delete_site_if_exists(self, site_name: str) -> bool:
        """
        Delete a site if it exists (idempotent).

        Args:
            site_name: Name of the site to delete

        Returns:
            bool: True if site was deleted, False if it didn't exist

        Raises:
            ConfigurationError: If site deletion fails
        """
        try:
            # Check if site exists using v1/sites/details
            if not self.gsdk.site_exists(site_name):
                LOG.info("Site '%s' does not exist, skipping deletion", site_name)
                return False

            # Get site ID for deletion
            site_id = self.gsdk.get_site_id(site_name)

            # Delete the site
            success = self.gsdk.delete_site(site_id)
            if success:
                LOG.info("Successfully deleted site '%s' with ID: %s", site_name, site_id)
                return True
            else:
                raise ConfigurationError(f"Failed to delete site '{site_name}' with ID: {site_id}")

        except Exception as e:
            LOG.error("Failed to delete site '%s': %s", site_name, str(e))
            raise ConfigurationError(f"Site deletion failed for {site_name}: {str(e)}")

    def attach_objects(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Attach global system objects to sites.

        Args:
            config_yaml_file: Path to the YAML file containing site attachment configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed
        """
        return self._manage_site_objects(config_yaml_file, operation="attach")

    def detach_objects(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Detach global system objects from sites.

        Args:
            config_yaml_file: Path to the YAML file containing site attachment configurations

        Returns:
            dict: Result with 'changed' status and details of operations performed
        """
        return self._manage_site_objects(config_yaml_file, operation="detach")

    def _manage_site_objects(self, config_yaml_file: str, operation: str) -> Dict[str, Any]:
        """
        Manage global system objects on sites (attach or detach).

        Args:
            config_yaml_file: Path to the YAML file containing site management definitions
            operation: Operation to perform - "attach" or "detach"

        Returns:
            dict: Result with 'changed' status and lists of attached/detached/skipped items

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        result: Dict[str, Any] = {"changed": False, "attached": [], "detached": [], "skipped": []}

        try:
            config_data = self.render_config_file(config_yaml_file)

            if "site_attachments" not in config_data:
                LOG.info(
                    "No site attachments configuration found in %s, skipping object %s", config_yaml_file, operation
                )
                return result

            default_operation = "Attach" if operation.lower().startswith("attach") else "Detach"
            attachment_site_names = [list(sc.keys())[0] for sc in (config_data.get("site_attachments") or []) if sc]
            if operation.lower().startswith("detach"):
                LOG.info("Attempting to detach objects from sites: %s", attachment_site_names)
            else:
                LOG.info("Attempting to attach objects to sites: %s", attachment_site_names)

            for site_config in config_data.get("site_attachments") or []:
                try:
                    # Get the site name from the first (and only) key in the site config
                    site_name = list(site_config.keys())[0]
                    site_data = site_config[site_name]

                    site_id = self.get_site_id(site_name)
                    site_payload = {"site": {"name": site_name}}

                    # Process SNMP operations
                    if "snmps" in site_data:
                        site_payload["site"]["snmpOps"] = {}
                        for snmp_name in site_data.get("snmps"):
                            site_payload["site"]["snmpOps"][snmp_name] = default_operation

                    # Process SNMP operations (Backward compatibility; Can be removed after testing)
                    if "snmp_servers" in site_data:
                        site_payload["site"]["snmpOps"] = {}
                        for snmp_name in site_data.get("snmp_servers"):
                            site_payload["site"]["snmpOps"][snmp_name] = default_operation

                    # Process Syslog operations
                    if "syslog_servers" in site_data:
                        site_payload["site"]["syslogServerOpsV2"] = {}
                        for syslog_config in site_data.get("syslog_servers"):
                            self._process_syslog_config(site_payload, syslog_config, default_operation)

                    # Process IPFIX operations
                    if "ipfix_exporters" in site_data:
                        site_payload["site"]["ipfixExporterOpsV2"] = {}
                        for ipfix_config in site_data.get("ipfix_exporters"):
                            self._process_ipfix_config(site_payload, ipfix_config, default_operation)

                    # Process NTP operations
                    if "ntps" in site_data:
                        site_payload["site"]["ntpOps"] = {}
                        for ntp_item in site_data.get("ntps") or []:
                            if isinstance(ntp_item, dict):
                                ntp_name = ntp_item.get("name")
                            else:
                                ntp_name = ntp_item
                            if ntp_name:
                                site_payload["site"]["ntpOps"][ntp_name] = default_operation

                    # Execute the site configuration
                    self.gsdk.post_site_config(site_id=site_id, site_config=site_payload)

                    # Mark as changed and track the operation
                    result["changed"] = True
                    if operation.lower().startswith("attach"):
                        result["attached"].append(site_name)
                    else:
                        result["detached"].append(site_name)

                    LOG.info(
                        "Successfully %s global objects for site: %s (ID: %s)",
                        default_operation.lower(),
                        site_name,
                        site_id,
                    )

                except SiteNotFoundError:
                    # For detach operations, site not found is acceptable (idempotent)
                    if operation.lower().startswith("detach"):
                        LOG.info("Site '%s' not found, skipping %s operation (idempotent)", site_name, operation)
                        result["skipped"].append(site_name)
                        continue
                    else:
                        LOG.error("Site '%s' not found, cannot %s objects", site_name, operation)
                        raise
                except Exception as e:
                    error_msg = str(e)
                    # Handle "already attached" errors gracefully
                    if operation.lower().startswith("attach") and (
                        "already attached" in error_msg.lower() or "already exists" in error_msg.lower()
                    ):
                        LOG.info(
                            "Object already %sed to site '%s', skipping: %s",
                            default_operation.lower(),
                            site_name,
                            error_msg,
                        )
                        result["skipped"].append(site_name)
                        continue
                    # Handle "already detached","not attached" and "not found" errors gracefully for detach operations
                    elif operation.lower().startswith("detach") and (
                        "already detached" in error_msg.lower()
                        or "not attached" in error_msg.lower()
                        or "not found" in error_msg.lower()
                    ):
                        LOG.info(
                            "Object not attached to site '%s', skipping %s: %s",
                            site_name,
                            default_operation.lower(),
                            error_msg,
                        )
                        result["skipped"].append(site_name)
                        continue
                    else:
                        LOG.error(
                            "Error %sing objects for site '%s': %s", default_operation.lower(), site_name, error_msg
                        )
                        raise ConfigurationError(f"Failed to {operation.lower()} objects for {site_name}: {error_msg}")

            total_processed = len(result["attached"]) + len(result["detached"]) + len(result["skipped"])
            LOG.info("Processed %s sites for object %s (changed: %s)", total_processed, operation, result["changed"])
            # Explicit lists for consistency with global_config/interface_manager deconfigure logging
            if operation.lower().startswith("detach"):
                LOG.info("Deconfigure completed: detached=%s, skipped=%s", result["detached"], result["skipped"])
            else:
                LOG.info("Configure completed: attached=%s, skipped=%s", result["attached"], result["skipped"])

            return result

        except Exception as e:
            LOG.error("Error in site %s operation: %s", operation, str(e))
            raise ConfigurationError(f"Site {operation} operation failed: {str(e)}")

    def _process_syslog_config(
        self, site_payload: Dict[str, Any], syslog_config: Union[str, Dict], default_operation: str
    ) -> None:
        """
        Process syslog configuration for site attachment/detachment.

        Args:
            site_payload: The site payload dictionary to update
            syslog_config: Syslog configuration (string or dict)
            default_operation: The operation to perform (Attach/Detach)
        """
        syslog_name: Optional[str]
        if isinstance(syslog_config, str):
            # Backward compatibility: simple string format
            syslog_name = syslog_config
            site_payload["site"]["syslogServerOpsV2"][syslog_name] = {"operation": default_operation}
        else:
            # New format: object with interface specification
            syslog_d = cast(Dict[str, Any], syslog_config)
            syslog_name = syslog_d.get("name")
            interface = syslog_d.get("interface")

            if not syslog_name:
                raise ValidationError("Syslog configuration must include 'name' field")

            site_payload["site"]["syslogServerOpsV2"][syslog_name] = {
                "operation": default_operation,
                "interface": {"interface": interface},
            }

    def _process_ipfix_config(
        self, site_payload: Dict[str, Any], ipfix_config: Union[str, Dict], default_operation: str
    ) -> None:
        """
        Process IPFIX configuration for site attachment/detachment.

        Args:
            site_payload: The site payload dictionary to update
            ipfix_config: IPFIX configuration (string or dict)
            default_operation: The operation to perform (Attach/Detach)
        """
        ipfix_name: Optional[str]
        if isinstance(ipfix_config, str):
            # Backward compatibility: simple string format
            ipfix_name = ipfix_config
            site_payload["site"]["ipfixExporterOpsV2"][ipfix_name] = {"operation": default_operation}
        else:
            # New format: object with interface specification
            ipfix_d = cast(Dict[str, Any], ipfix_config)
            ipfix_name = ipfix_d.get("name")
            interface = ipfix_d.get("interface")

            if not ipfix_name:
                raise ValidationError("IPFIX configuration must include 'name' field")

            site_payload["site"]["ipfixExporterOpsV2"][ipfix_name] = {
                "operation": default_operation,
                "interface": {"interface": interface},
            }
