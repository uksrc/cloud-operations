"""
BGP Manager for Graphiant Playbooks.

This module handles BGP peering configuration management,
including policy attachment and detachment.
"""

from typing import Any, Dict

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class BGPManager(BaseManager):
    """
    Manages BGP peering configurations.

    Handles the configuration, deconfiguration, and policy management
    for BGP peering relationships.
    """

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure BGP peers for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing BGP peering configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {"changed": False, "configured_devices": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            final_config_payload = {}

            if "bgp_peering" not in config_data:
                LOG.warning("No BGP peering configuration found in %s", config_yaml_file)
                return result

            for device_config in config_data.get("bgp_peering") or []:
                for device_name, config in device_config.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )
                        config_payload: Dict[str, Any] = {}
                        self.config_utils.device_bgp_peering(config_payload, **config)

                        final_config_payload[device_id] = {"device_id": device_id, "edge": config_payload}

                        LOG.info("Configured BGP peering for device: %s (ID: %s)", device_name, device_id)

                    except DeviceNotFoundError:
                        LOG.error("Device '%s' not found, skipping BGP configuration", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error configuring BGP for device '%s': %s", device_name, str(e))
                        raise ConfigurationError(f"Failed to configure BGP for {device_name}: {str(e)}")

            if final_config_payload:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, final_config_payload)
                result["changed"] = True
                result["configured_devices"] = list(final_config_payload.keys())
                LOG.info("Successfully configured BGP peering for %s devices", len(final_config_payload))
            else:
                LOG.warning("No valid BGP configurations found")

            return result

        except Exception as e:
            LOG.error("Error in BGP configuration: %s", str(e))
            raise ConfigurationError(f"BGP configuration failed: {str(e)}")

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure BGP peers for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing BGP peering configurations

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices
            Note: Always returns changed=True when devices are deconfigured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {"changed": False, "deconfigured_devices": []}

        try:
            config_data = self.render_config_file(config_yaml_file)
            final_config_payload = {}

            if "bgp_peering" not in config_data:
                LOG.warning("No BGP peering configuration found in %s", config_yaml_file)
                return result

            for device_config in config_data.get("bgp_peering") or []:
                for device_name, config in device_config.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )
                        config_payload: Dict[str, Any] = {}
                        self.config_utils.device_bgp_peering(config_payload, action="delete", **config)

                        final_config_payload[device_id] = {"device_id": device_id, "edge": config_payload}

                        LOG.info("Deconfigured BGP peering for device: %s (ID: %s)", device_name, device_id)

                    except DeviceNotFoundError:
                        LOG.error("Device '%s' not found, skipping BGP deconfiguration", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring BGP for device '%s': %s", device_name, str(e))
                        raise ConfigurationError(f"Failed to deconfigure BGP for {device_name}: {str(e)}")

            if final_config_payload:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, final_config_payload)
                result["changed"] = True
                result["deconfigured_devices"] = list(final_config_payload.keys())
                LOG.info("Successfully deconfigured BGP peering for %s devices", len(final_config_payload))
            else:
                LOG.warning("No valid BGP configurations found")

            return result

        except Exception as e:
            LOG.error("Error in BGP deconfiguration: %s", str(e))
            raise ConfigurationError(f"BGP deconfiguration failed: {str(e)}")

    def detach_policies(self, config_yaml_file: str) -> None:
        """
        Detach routing policies from BGP peers.

        Args:
            config_yaml_file: Path to the YAML file containing BGP peering configurations

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            final_config_payload = {}

            if "bgp_peering" not in config_data:
                LOG.warning("No BGP peering configuration found in %s", config_yaml_file)
                return

            for device_config in config_data.get("bgp_peering") or []:
                for device_name, config in device_config.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )
                        config_payload: Dict[str, Any] = {}
                        self.config_utils.device_bgp_peering(config_payload, action="unlink", **config)

                        final_config_payload[device_id] = {"device_id": device_id, "edge": config_payload}

                        LOG.info("Detached policies from BGP peers for device: %s (ID: %s)", device_name, device_id)

                    except DeviceNotFoundError:
                        LOG.error("Device '%s' not found, skipping policy detachment", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error detaching policies for device '%s': %s", device_name, str(e))
                        raise ConfigurationError(f"Failed to detach policies for {device_name}: {str(e)}")

            if final_config_payload:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, final_config_payload)
                LOG.info("Successfully detached policies from BGP peers for %s devices", len(final_config_payload))
            else:
                LOG.warning("No valid BGP configurations found")

        except Exception as e:
            LOG.error("Error in policy detachment: %s", str(e))
            raise ConfigurationError(f"Policy detachment failed: {str(e)}")

    # Backward compatibility methods
    def configure_bgp_peers(self, config_yaml_file: str) -> None:
        """Alias for configure method for backward compatibility."""
        self.configure(config_yaml_file)

    def deconfigure_bgp_peers(self, config_yaml_file: str) -> None:
        """Alias for deconfigure method for backward compatibility."""
        self.deconfigure(config_yaml_file)

    def detach_policies_from_bgp_peers(self, config_yaml_file: str) -> None:
        """Alias for detach_policies method for backward compatibility."""
        self.detach_policies(config_yaml_file)
