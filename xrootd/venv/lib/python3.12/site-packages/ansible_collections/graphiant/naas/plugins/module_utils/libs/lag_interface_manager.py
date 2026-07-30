"""
LAG Interfaces Manager for Graphiant Playbooks.

This module handles LAG (Link Aggregation Group) interface configuration management
for Graphiant Edge/Gateway devices.

Idempotency Support:
    All operations in this module are idempotent and safe to run multiple times:
    - configure (add): Creates new LAGs or updates existing ones. Handles duplicate
      alias assignments by removing alias from payload when it matches existing.
    - deconfigure: Skips LAGs that don't exist.
    - add_lag_members: Skips members already present in the LAG.
    - remove_lag_members: Skips members already removed from the LAG.
    - update_lacp_configs: Skips if LACP mode/timer already match desired state.
    - delete_lag_subinterfaces: Deletes specified subinterfaces.
"""

from typing import Any, Dict

from .base_manager import BaseManager
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()


class LagInterfaceManager(BaseManager):

    @staticmethod
    def _get_existing_lag_info(gcs_device_info):
        """
        Get existing LAG interface information from device info.

        LAG interfaces are regular interfaces in the device.interfaces array
        that have the lag_interface property set. Subinterfaces are also captured
        with their aliases (name format: LAG1.101).

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()

        Returns:
            dict: Dictionary mapping LAG name to its properties including subinterfaces
                  e.g., {'LAG1': {'alias': 'LAG1', 'subinterfaces': {101: {'alias': 'LAG1-101'}}}}
        """
        existing_lags = {}
        if not hasattr(gcs_device_info, "device"):
            return existing_lags

        device = gcs_device_info.device

        # First pass: Find all LAG main interfaces and their nested subinterfaces
        if hasattr(device, "interfaces") and device.interfaces:
            # Debug: Log all interface names that contain 'LAG'
            lag_related_names = [
                getattr(i, "name", "N/A") for i in device.interfaces if "LAG" in str(getattr(i, "name", ""))
            ]
            LOG.info("_get_existing_lag_info: All LAG-related interface names: %s", lag_related_names)
            for interface in device.interfaces:
                if hasattr(interface, "lag_interface") and interface.lag_interface:
                    interface_name = getattr(interface, "name", None)
                    if interface_name:
                        # Get LAG member IDs and LACP config if available
                        lag_member_ids = set()
                        lacp_config = {}
                        lag_intf_obj = getattr(interface, "lag_interface", None)
                        if lag_intf_obj:
                            if hasattr(lag_intf_obj, "members") and lag_intf_obj.members:
                                for member in lag_intf_obj.members:
                                    # Members can be integers (the ID directly) or objects with an id attribute
                                    if isinstance(member, int):
                                        lag_member_ids.add(member)
                                    else:
                                        member_id = getattr(member, "id", None) or getattr(member, "interface_id", None)
                                        if member_id:
                                            lag_member_ids.add(member_id)
                                LOG.info(
                                    "_get_existing_lag_info: LAG '%s' has %d member(s): %s",
                                    interface_name,
                                    len(lag_member_ids),
                                    list(lag_member_ids),
                                )
                            # Get LACP config (mode, timer)
                            lacp_cfg_obj = getattr(lag_intf_obj, "lacp_config", None)
                            if lacp_cfg_obj:
                                lacp_config = {
                                    "mode": getattr(lacp_cfg_obj, "mode", None),
                                    "timer": getattr(lacp_cfg_obj, "timer", None),
                                }
                                LOG.info(
                                    "_get_existing_lag_info: LAG '%s' LACP config: %s", interface_name, lacp_config
                                )
                        existing_lags[interface_name] = {
                            "alias": getattr(interface, "alias", None),
                            "id": getattr(interface, "id", None),
                            "subinterfaces": {},
                            "member_ids": lag_member_ids,
                            "lacp_config": lacp_config,
                        }
                        # Debug: Log all attributes of the LAG interface to find subinterfaces
                        lag_attrs = [
                            attr
                            for attr in dir(interface)
                            if not attr.startswith("_") and not callable(getattr(interface, attr, None))
                        ]
                        LOG.debug("_get_existing_lag_info: LAG '%s' attributes: %s", interface_name, lag_attrs)
                        # Check for subinterfaces as a nested property on the LAG interface
                        # Note: The attribute is 'subinterfaces' (no underscore)
                        subinterfaces_list = getattr(interface, "subinterfaces", None)
                        if subinterfaces_list:
                            for sub_intf in subinterfaces_list:
                                sub_vlan = getattr(sub_intf, "vlan", None)
                                sub_alias = getattr(sub_intf, "alias", None)
                                if sub_vlan is not None:
                                    existing_lags[interface_name]["subinterfaces"][sub_vlan] = {
                                        "alias": sub_alias,
                                        "id": getattr(sub_intf, "id", None),
                                    }
                                    LOG.info(
                                        "_get_existing_lag_info: Found nested subinterface vlan %s "
                                        "with alias '%s' on LAG '%s'",
                                        sub_vlan,
                                        sub_alias,
                                        interface_name,
                                    )

            # Second pass: Find all LAG subinterfaces as separate entries (format: LAG1.101)
            # Some APIs may return subinterfaces as separate interface entries
            for interface in device.interfaces:
                interface_name = getattr(interface, "name", None)
                if interface_name and "." in interface_name:
                    # This is a subinterface, check if parent is a LAG
                    parent_name, vlan_str = interface_name.rsplit(".", 1)
                    if parent_name in existing_lags:
                        try:
                            vlan = int(vlan_str)
                            # Only add if not already found via nested property
                            if vlan not in existing_lags[parent_name]["subinterfaces"]:
                                interface_alias = getattr(interface, "alias", None)
                                existing_lags[parent_name]["subinterfaces"][vlan] = {
                                    "alias": interface_alias,
                                    "id": getattr(interface, "id", None),
                                }
                                LOG.info(
                                    "_get_existing_lag_info: Found subinterface %s with alias '%s'",
                                    interface_name,
                                    interface_alias,
                                )
                        except ValueError:
                            pass  # Not a valid vlan number

        if existing_lags:
            LOG.info("_get_existing_lag_info: Found existing LAGs: %s", list(existing_lags.keys()))

        return existing_lags

    def configure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Configure LAG interfaces for multiple devices concurrently (idempotent).

        Creates new LAGs or updates existing ones. Automatically handles duplicate
        alias assignments by removing alias from payload when it matches existing.
        Subinterface aliases are also handled to prevent duplicate alias errors.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device IDs.
                - created_lags (list): LAGs that were newly created.
                - updated_lags (list): LAGs that were updated.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add")

    def deconfigure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Deconfigure LAG interfaces for multiple devices concurrently (idempotent).

        Deletes subinterfaces first, then removes the LAG. Skips LAGs that
        don't exist on the device.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - deconfigured_devices (list): List of affected device IDs.
                - deconfigured_lags (list): LAGs that were removed.
                - skipped_lags (list): LAGs that were skipped (not found).

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.deconfigure_lag_interfaces(config_yaml_file)

    def add_lag_members(self, config_yaml_file: str) -> dict:
        """
        Add interface members to an existing LAG for multiple devices (idempotent).

        Skips members that are already present in the LAG. If all specified
        members are already added, no API call is made for that LAG.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had members added.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add_lag_members")

    def remove_lag_members(self, config_yaml_file: str) -> dict:
        """
        Remove interface members from an existing LAG for multiple devices (idempotent).

        Skips members that are already removed from the LAG. If all specified
        members are already absent, no API call is made for that LAG.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had members removed.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="remove_lag_members")

    def update_lacp_configs(self, config_yaml_file: str) -> dict:
        """
        Update LACP parameters (mode/timer) for LAGs across devices (idempotent).

        Compares current LACP mode and timer with desired values. Skips LAGs
        where the configuration already matches. Case-insensitive comparison
        is used for mode and timer values.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had LACP config updated.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="update_lacp_configs")

    def delete_lag_subinterfaces(self, config_yaml_file: str) -> dict:
        """
        Delete VLAN subinterfaces under a LAG for multiple devices concurrently (idempotent).

        Skips deletion if:
        - The LAG does not exist.
        - The subinterface does not exist.
        - All specified subinterfaces are already deleted.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.
                - updated_lags (list): LAGs that had subinterfaces deleted.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="delete")

    def configure_lag_interfaces(self, config_yaml_file: str, action: str = "add") -> dict:
        """
        Configure/update LAG interfaces for multiple devices concurrently (idempotent).

        This is the core method that handles all LAG configuration operations with
        built-in idempotency checks:
            - add: Creates or updates LAGs. Handles duplicate aliases automatically.
            - add_lag_members: Skips already-present members.
            - remove_lag_members: Skips already-absent members.
            - update_lacp_configs: Skips if mode/timer already match.
            - delete: Deletes subinterfaces under LAG.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.
            action: Action string passed through to the template renderer.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device IDs.
                - created_lags (list): LAGs newly created (for 'add' action).
                - updated_lags (list): LAGs updated or modified.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        try:
            result: Dict[str, Any] = {
                "changed": False,
                "configured_devices": [],
                "created_lags": [],
                "updated_lags": [],
            }

            config_data = self.render_config_file(config_yaml_file)
            output_config = {}
            device_configs: Dict[str, Any] = {}
            # Cache for device info to avoid redundant API calls
            device_info_cache = {}

            if "lagInterfaces" not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = []
                    device_configs[device_name].extend(config_list)

            for device_name, configs in device_configs.items():
                LOG.info("Processing device: %s (%d LAG config(s))", device_name, len(configs))

                # Get device_id once per device
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        "Please check device name and enterprise credentials."
                    )

                # Get device info once per device (use cache if available)
                if device_id not in device_info_cache:
                    device_info_cache[device_id] = self.gsdk.get_device_info(device_id)
                gcs_device_info = device_info_cache[device_id]

                # Get existing LAG info once per device
                existing_lags = self._get_existing_lag_info(gcs_device_info)

                for config in configs:
                    try:
                        lag_name = config.get("name")

                        # If LAG already exists, check if alias needs to be removed to avoid
                        # "cannot assign alias LAG1 to LAG1 as that alias is in use" error
                        if lag_name in existing_lags:
                            existing_lag_info = existing_lags[lag_name]
                            existing_alias = existing_lag_info.get("alias")
                            config_alias = config.get("alias")

                            # If alias in config matches existing alias, remove it
                            # to avoid the duplicate alias error during update
                            if config_alias and config_alias == existing_alias:
                                LOG.info(
                                    "Removing unchanged alias '%s' from LAG '%s' config "
                                    "to avoid duplicate alias error",
                                    config_alias,
                                    lag_name,
                                )
                                config.pop("alias", None)

                            # Also check subinterface aliases
                            existing_subinterfaces = existing_lag_info.get("subinterfaces", {})
                            LOG.info("Existing subinterfaces for LAG '%s': %s", lag_name, existing_subinterfaces)
                            _subinterfaces = config.get("subinterfaces") or config.get("sub_interfaces")
                            if _subinterfaces:
                                LOG.info(
                                    "Config subinterfaces for LAG '%s': %s",
                                    lag_name,
                                    [{"vlan": s.get("vlan"), "alias": s.get("alias")} for s in _subinterfaces],
                                )
                                for subinterface in _subinterfaces:
                                    vlan = subinterface.get("vlan")
                                    # Convert vlan to int for comparison (existing_subinterfaces keys are ints)
                                    try:
                                        vlan_int = int(vlan) if vlan is not None else None
                                    except (ValueError, TypeError):
                                        vlan_int = None
                                    if vlan_int and vlan_int in existing_subinterfaces:
                                        existing_sub_alias = existing_subinterfaces[vlan_int].get("alias")
                                        config_sub_alias = subinterface.get("alias")
                                        if config_sub_alias and config_sub_alias == existing_sub_alias:
                                            LOG.info(
                                                "Removing unchanged alias '%s' from LAG '%s' "
                                                "subinterface vlan %s to avoid duplicate alias error",
                                                config_sub_alias,
                                                lag_name,
                                                vlan,
                                            )
                                            subinterface.pop("alias", None)

                        # Get the interface IDs for the interface members
                        config["interfaceMemberIds"] = []
                        lag_members_config = config.get("lagMembers", [])

                        # Check if lagMembers is required but not specified
                        if action in ("add_lag_members", "remove_lag_members") and not lag_members_config:
                            LOG.warning(
                                "[%s] No 'lagMembers' specified for LAG '%s' on device '%s'. "
                                "Skipping LAG member operation.",
                                action,
                                lag_name,
                                device_name,
                            )
                            # For add action, we still process the LAG (just without members)
                            # For add_lag_members/remove_lag_members, skip entirely
                            if action in ("add_lag_members", "remove_lag_members"):
                                continue

                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in lag_members_config:
                                config["interfaceMemberIds"].append(interface_info.id)

                        # Get existing member IDs for idempotency checks
                        existing_member_ids = existing_lags.get(lag_name, {}).get("member_ids", set())

                        # Idempotency check for add_lag_members:
                        # Only include member IDs that are NOT already in the LAG
                        if action == "add_lag_members" and lag_name in existing_lags:
                            LOG.info(
                                "[add_lag_members] Existing member IDs in LAG '%s': %s",
                                lag_name,
                                list(existing_member_ids),
                            )
                            original_member_ids = config["interfaceMemberIds"][:]
                            config["interfaceMemberIds"] = [
                                mid for mid in config["interfaceMemberIds"] if mid not in existing_member_ids
                            ]
                            skipped_ids = set(original_member_ids) - set(config["interfaceMemberIds"])
                            if skipped_ids:
                                LOG.info(
                                    "[add_lag_members] Skipping already added members to LAG '%s' "
                                    "on device '%s': %s",
                                    lag_name,
                                    device_name,
                                    list(skipped_ids),
                                )
                            if not config["interfaceMemberIds"]:
                                LOG.info(
                                    "[add_lag_members] All members already added to LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip this LAG config, nothing to add

                        # Idempotency check for remove_lag_members:
                        # Only include member IDs that actually exist in the LAG
                        if action == "remove_lag_members" and lag_name in existing_lags:
                            LOG.info(
                                "[remove_lag_members] Existing member IDs in LAG '%s': %s",
                                lag_name,
                                list(existing_member_ids),
                            )
                            original_member_ids = config["interfaceMemberIds"][:]
                            config["interfaceMemberIds"] = [
                                mid for mid in config["interfaceMemberIds"] if mid in existing_member_ids
                            ]
                            skipped_ids = set(original_member_ids) - set(config["interfaceMemberIds"])
                            if skipped_ids:
                                LOG.info(
                                    "[remove_lag_members] Skipping already removed members from LAG '%s' "
                                    "on device '%s': %s",
                                    lag_name,
                                    device_name,
                                    list(skipped_ids),
                                )
                            if not config["interfaceMemberIds"]:
                                LOG.info(
                                    "[remove_lag_members] All members already removed from LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip this LAG config, nothing to remove

                        # Idempotency check for update_lacp_configs:
                        # Skip if LACP config (mode, timer) matches existing config
                        if action == "update_lacp_configs" and lag_name in existing_lags:
                            existing_lacp = existing_lags[lag_name].get("lacp_config", {})
                            # Config uses lacpMode/lacpTimer (not nested lacpConfigs)
                            desired_mode = config.get("lacpMode")
                            desired_timer = config.get("lacpTimer")
                            existing_mode = existing_lacp.get("mode")
                            existing_timer = existing_lacp.get("timer")

                            LOG.info(
                                "[update_lacp_configs] LAG '%s' - Existing LACP: mode=%s, timer=%s | "
                                "Desired LACP: mode=%s, timer=%s",
                                lag_name,
                                existing_mode,
                                existing_timer,
                                desired_mode,
                                desired_timer,
                            )

                            # Check if both mode and timer match (case-insensitive comparison)
                            # If desired is not specified (None), we can't compare, so don't skip
                            if desired_mode is None and desired_timer is None:
                                LOG.warning(
                                    "[update_lacp_configs] No lacpMode/lacpTimer specified for LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip - nothing to update

                            mode_matches = desired_mode is None or (
                                existing_mode and desired_mode.upper() == existing_mode.upper()
                            )
                            timer_matches = desired_timer is None or (
                                existing_timer and desired_timer.upper() == existing_timer.upper()
                            )

                            if mode_matches and timer_matches:
                                LOG.info(
                                    "[update_lacp_configs] LACP config already matches for LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip this LAG config, nothing to update

                        # Idempotency check for delete action (delete_lag_subinterfaces):
                        # Only delete subinterfaces that actually exist
                        if action == "delete":
                            # Check if LAG exists
                            if lag_name not in existing_lags:
                                LOG.info(
                                    "[delete] LAG '%s' does not exist on device '%s', skipping", lag_name, device_name
                                )
                                continue  # Skip - LAG doesn't exist

                            # Check if subinterfaces exist
                            existing_subinterfaces = existing_lags[lag_name].get("subinterfaces", {})
                            _subinterfaces = config.get("subinterfaces") or config.get("sub_interfaces")

                            if not _subinterfaces:
                                LOG.warning(
                                    "[delete] No 'subinterfaces' specified for LAG '%s' on device '%s'. "
                                    "Skipping subinterface deletion.",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip - no subinterfaces to delete

                            # Filter subinterfaces to only include those that exist
                            subinterfaces_to_delete = []
                            for subinterface in _subinterfaces:
                                vlan = subinterface.get("vlan")
                                try:
                                    vlan_int = int(vlan) if vlan is not None else None
                                except (ValueError, TypeError):
                                    vlan_int = None

                                if vlan_int and vlan_int in existing_subinterfaces:
                                    subinterfaces_to_delete.append(subinterface)
                                    LOG.info(
                                        "[delete] Subinterface vlan %s exists on LAG '%s', will delete",
                                        vlan_int,
                                        lag_name,
                                    )
                                else:
                                    LOG.info(
                                        "[delete] Subinterface vlan %s does not exist on LAG '%s', skipping",
                                        vlan,
                                        lag_name,
                                    )

                            if not subinterfaces_to_delete:
                                LOG.info(
                                    "[delete] All subinterfaces already deleted from LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                continue  # Skip - nothing to delete

                            # Update config to only include subinterfaces that exist
                            config["subinterfaces"] = subinterfaces_to_delete

                        # Only initialize output_config AFTER all skip checks pass
                        # Also, only initialize if device_id not already present, otherwise it will be overwritten.
                        if device_id not in output_config:
                            output_config[device_id] = {"device_id": device_id, "edge": {"lagInterfaces": {}}}

                        self.config_utils.lag_interfaces(output_config[device_id]["edge"], action=action, **config)

                        # Track whether this is a create or update operation
                        if lag_name in existing_lags:
                            result["updated_lags"].append({"device": device_name, "lag": lag_name})
                            LOG.info(
                                "[configure] Updating LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                            )
                        else:
                            result["created_lags"].append({"device": device_name, "lag": lag_name})
                            LOG.info(
                                "[configure] Creating LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                            )

                        if device_id not in result["configured_devices"]:
                            result["configured_devices"].append(device_id)
                    except ConfigurationError:
                        raise
                    except Exception as e:
                        LOG.error("Error configuring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True

            LOG.info(
                "LAG interface configuration completed: %s created, %s updated (changed: %s)",
                len(result["created_lags"]),
                len(result["updated_lags"]),
                result["changed"],
            )

            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in LAG interface configuration: %s", str(e))
            raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")

    def deconfigure_lag_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deconfigure (remove) LAG interfaces for multiple devices concurrently (idempotent).

        Performs a two-step deletion: first deletes all subinterfaces, then deletes
        the main LAG interface. Skips LAGs that don't exist on the device.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - deconfigured_devices (list): List of affected device IDs.
                - deconfigured_lags (list): LAGs that were successfully removed.
                - skipped_lags (list): LAGs skipped because they don't exist.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        try:
            result: Dict[str, Any] = {
                "changed": False,
                "deconfigured_devices": [],
                "deconfigured_lags": [],
                "skipped_lags": [],
            }

            config_data = self.render_config_file(config_yaml_file)
            del_lag_subinterfaces_config = {}
            del_lag_interface_config = {}
            device_configs: Dict[str, Any] = {}
            # Cache for device info to avoid redundant API calls
            device_info_cache = {}

            if "lagInterfaces" not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = []
                    device_configs[device_name].extend(config_list)

            lag_names_per_device = {d: [c.get("name") for c in configs] for d, configs in device_configs.items()}
            LOG.info(
                "Attempting to deconfigure LAG interfaces for devices: %s (LAGs: %s)",
                list(device_configs.keys()),
                lag_names_per_device,
            )

            for device_name, configs in device_configs.items():
                LOG.info("Processing device: %s (%d LAG config(s) to be deconfigured)", device_name, len(configs))

                # Get device_id once per device (outside inner loop)
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        "Please check device name and enterprise credentials."
                    )

                # Get device info once per device (use cache if available)
                if device_id not in device_info_cache:
                    device_info_cache[device_id] = self.gsdk.get_device_info(device_id)
                gcs_device_info = device_info_cache[device_id]

                # Get existing LAG info once per device
                existing_lags = self._get_existing_lag_info(gcs_device_info)

                """
                Note: To delete LAG main interface with subinterfaces, we need to delete the subinterfaces first
                and then delete the main interface.

                Example payload to delete subinterfaces:
                {"edge":{"lagInterfaces":{"LAG1":{"interface":{"subinterfaces":{"101":{"interface":null},
                "102":{"interface":null}}}}}},"description":"","configurationMetadata":{"name":""}}

                Example payload to delete main interface:
                {"edge":{"interfaces":{"LAG1":{"interface":null}}},"description":"","configurationMetadata":{"name":""}}
                """

                for config in configs:
                    try:
                        lag_name = config.get("name")

                        # Check if LAG exists - skip if it doesn't (idempotent)
                        if lag_name not in existing_lags:
                            LOG.info(
                                " ✓ LAG '%s' does not exist on device '%s' - skipping (idempotent)",
                                lag_name,
                                device_name,
                            )
                            result["skipped_lags"].append(
                                {"device": device_name, "lag": lag_name, "reason": "does not exist"}
                            )
                            continue

                        # Only initialize if device_id not already present, otherwise it will be overwritten.
                        if device_id not in del_lag_subinterfaces_config:
                            del_lag_subinterfaces_config[device_id] = {
                                "device_id": device_id,
                                "edge": {"lagInterfaces": {}},
                            }

                        if device_id not in del_lag_interface_config:
                            del_lag_interface_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                        # Get the interface IDs for the interface members
                        config["interfaceMemberIds"] = []
                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in config.get("lagMembers", []):
                                config["interfaceMemberIds"].append(interface_info.id)

                        # Deconfigure deletes ALL existing subinterfaces (not just those in config)
                        # This is a complete cleanup operation
                        existing_subinterfaces = existing_lags[lag_name].get("subinterfaces", {})

                        if existing_subinterfaces:
                            # Build subinterfaces list from all existing subinterfaces
                            subinterfaces_to_delete = []
                            for vlan_int, subif_info in existing_subinterfaces.items():
                                subinterfaces_to_delete.append({"vlan": vlan_int})
                                LOG.info(
                                    "[deconfigure] Subinterface vlan %s exists on LAG '%s', will delete",
                                    vlan_int,
                                    lag_name,
                                )

                            # Add all existing subinterfaces to config for deletion
                            config["subinterfaces"] = subinterfaces_to_delete
                            self.config_utils.lag_interfaces(
                                del_lag_subinterfaces_config[device_id]["edge"], action="delete", **config
                            )
                        else:
                            LOG.info(
                                "[deconfigure] LAG '%s' has no subinterfaces, skipping subinterface deletion step",
                                lag_name,
                            )

                        # Delete the main LAG interface
                        self.config_utils.lag_interfaces(
                            del_lag_interface_config[device_id]["edge"], action="delete_lag", **config
                        )

                        result["deconfigured_lags"].append({"device": device_name, "lag": lag_name})
                        if device_id not in result["deconfigured_devices"]:
                            result["deconfigured_devices"].append(device_id)

                        LOG.info(
                            "[deconfigure] Processing LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                        )
                    except ConfigurationError:
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")

            if del_lag_subinterfaces_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, del_lag_subinterfaces_config)
                result["changed"] = True

            if del_lag_interface_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, del_lag_interface_config)
                result["changed"] = True

            LOG.info(
                "LAG interface deconfiguration completed: %s deleted, %s skipped (changed: %s)",
                len(result["deconfigured_lags"]),
                len(result["skipped_lags"]),
                result["changed"],
            )
            # Explicit lists for consistency with global_config deconfigure logging
            LOG.info(
                "Deconfigure completed: deconfigured_lags=%s, skipped_lags=%s",
                [e.get("lag") for e in result["deconfigured_lags"]],
                [e.get("lag") for e in result["skipped_lags"]],
            )

            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in LAG interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")
