"""
Device Config Manager for Graphiant Playbooks

This module provides functionality for pushing device configurations directly
to multiple devices using the /v1/devices/{device_id}/config API.

Unlike template-based managers (InterfaceManager, BGPManager), this manager
processes configuration payloads directly from the config file, similar to
DataExchangeManager. Users can capture API payloads from the Graphiant Portal
UI developer tools and use them directly.

Key Features:
- Push raw device configuration to multiple devices concurrently
- Optional user-defined Jinja2 templates for configuration generation
- Configuration preview before actual push
- Supports all config file Jinja2 templating
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, NoReturn, Optional


def _load_device_config_jinja2():
    """Load Jinja2 Template + error class without reassigning imported names in try/except (mypy)."""
    try:
        from jinja2 import Template, TemplateError as Jinja2TemplateError

        return Template, Jinja2TemplateError, True
    except ImportError:
        return None, type("Jinja2TemplateError", (Exception,), {}), False


Template, Jinja2TemplateError, HAS_JINJA2 = _load_device_config_jinja2()

from .base_manager import BaseManager  # noqa: E402
from .logger import setup_logger  # noqa: E402
from .exceptions import ConfigurationError, DeviceNotFoundError  # noqa: E402

LOG = setup_logger()


class DeviceConfigManager(BaseManager):
    """
    Manager for pushing device configurations directly to devices.

    This manager handles the following operations:
    - configure: Push device configuration to devices (PUT /v1/devices/{device_id}/config)
    - show_validated_payload: Show validated device configuration payload using SDK models
      (PUT /v1/devices/{device_id}/config-preview)

    Configuration files support Jinja2 templating. The config file format:

    device_config:
      - device-name-1:
          payload: |
            {
              "edge": { ... },
              "description": "...",
              "configurationMetadata": { "name": "..." }
            }
      - device-name-2:
          payload: |
            { ... }

    Optionally, a user-defined template file can be provided to generate
    the final payload from simplified config data.
    """

    def configure(self, config_yaml_file: str, template_file=None) -> dict:
        """
        Configure devices by pushing configuration payloads.

        This method reads the configuration file, optionally renders it with
        a user-defined template, and pushes the configuration to each device.

        Args:
            config_yaml_file: Path to the YAML configuration file containing device_config
            template_file: Optional path to a user-defined Jinja2 template file

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "configured_devices": [], "skipped_devices": []}

        LOG.info("Configuring devices from %s", config_yaml_file)
        if template_file:
            LOG.info("Using user-defined template: %s", template_file)

        try:
            # Load and process configuration
            device_configs = self._load_device_configs(config_yaml_file, template_file)

            if not device_configs:
                LOG.warning("No device_config found in configuration file")
                return result

            # Print current enterprise info
            LOG.info("DeviceConfigManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            # Build the config payload for concurrent execution
            output_config = {}
            device_names = {}  # Map device_id -> device_name for result tracking

            for device_name, config_data in device_configs.items():
                LOG.info("Processing device: %s", device_name)

                # Get device ID
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise DeviceNotFoundError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        f"Please check device name and enterprise credentials."
                    )

                # Parse the payload
                payload = self._parse_payload(config_data, device_name)
                if payload is None:
                    LOG.warning("Skipping device '%s' - no valid payload", device_name)
                    result["skipped_devices"].append(device_name)
                    continue

                # Build output config for concurrent execution
                output_config[device_id] = {"device_id": device_id, "payload": payload}
                device_names[device_id] = device_name
                LOG.info(" ✓ Prepared configuration for device: %s (ID: %s)", device_name, device_id)

            # Execute concurrent configuration push
            if output_config:
                LOG.info("Showing validated payload for %d device(s)...", len(output_config))
                self.execute_concurrent_tasks(self.gsdk.show_validated_payload, output_config)
                LOG.info("Pushing configuration to %d device(s)...", len(output_config))
                self.execute_concurrent_tasks(self.gsdk.put_device_config_raw, output_config)
                result["changed"] = True
                result["configured_devices"] = [device_names[did] for did in output_config.keys()]
                LOG.info(
                    "Successfully configured %d device(s), skipped %d",
                    len(result["configured_devices"]),
                    len(result["skipped_devices"]),
                )
            else:
                LOG.warning("No devices to configure")

            return result

        except (ConfigurationError, DeviceNotFoundError):
            raise
        except Exception as e:
            LOG.error("Failed to configure devices: %s", str(e))
            import traceback

            LOG.error("Traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"Device configuration failed: {str(e)}")

    def show_validated_payload(self, config_yaml_file: str, template_file=None) -> Dict[str, Any]:
        """
        Show validated device configuration payload using SDK models (dry-run mode).

        This method reads the configuration file, optionally renders it with
        a user-defined template and validates the configuration structure using
        SDK models without pushing the configuration. This returns the validated payload.

        Note: This validates payload using SDK models locally. A future
        'configure_preview' operation will use PUT /v1/devices/{deviceId}/config-preview
        API for backend validation.

        This is useful for:
        - Validating configuration file syntax and structure
        - Verifying payload conforms to SDK model schema
        - Verifying device names resolve to valid device IDs

        Args:
            config_yaml_file: Path to the YAML configuration file containing device_config
            template_file: Optional path to a user-defined Jinja2 template file

        Returns:
            Dict containing validation results for each device

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info("Validating device configuration from %s (dry-run mode)", config_yaml_file)
        if template_file:
            LOG.info("Using user-defined template: %s", template_file)

        try:
            # Load and process configuration
            device_configs = self._load_device_configs(config_yaml_file, template_file)

            if not device_configs:
                LOG.warning("No device_config found in configuration file")
                return {}

            # Print current enterprise info
            LOG.info("DeviceConfigManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            # Build the config payload for concurrent validation
            output_config = {}
            validated_count = 0

            for device_name, config_data in device_configs.items():
                LOG.info("Processing device: %s to show validated payload", device_name)

                # Get device ID
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise DeviceNotFoundError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        f"Please check device name and enterprise credentials."
                    )

                # Parse the payload
                payload = self._parse_payload(config_data, device_name)
                if payload is None:
                    LOG.warning("Skipping device '%s' - no valid payload", device_name)
                    continue

                # Build output config for concurrent validation
                output_config[device_id] = {"device_id": device_id, "payload": payload}
                validated_count += 1
                LOG.info(" ✓ Configuration parsed for device: %s (ID: %s)", device_name, device_id)

            # Execute concurrent configuration validation
            if output_config:
                LOG.info("Showing validated payload for %d device(s)...", len(output_config))
                results = self.execute_concurrent_tasks(self.gsdk.show_validated_payload, output_config)
                LOG.info("Successfully showed validated payload for %d device(s) - DRY-RUN complete", validated_count)
                LOG.info("No configuration was pushed. Use 'configure' operation to apply changes.")
                return results
            else:
                LOG.warning("No devices to validate")
                return {}

        except (ConfigurationError, DeviceNotFoundError):
            raise
        except Exception as e:
            LOG.error("Failed to validate device configuration: %s", str(e))
            import traceback

            LOG.error("Traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"Device configuration validation failed: {str(e)}")

    def deconfigure(self, config_yaml_file: str) -> NoReturn:
        """
        Deconfigure is not supported for device config.

        Device configuration is a PUT operation that replaces configuration.
        There is no specific "deconfigure" operation - users should push
        a new configuration to change device settings.

        Args:
            config_yaml_file: Path to the YAML configuration file (not used)

        Raises:
            ConfigurationError: Always raises as deconfigure is not supported
        """
        raise ConfigurationError(
            "Deconfigure is not supported for device configuration. "
            "To reset or change device configuration, use the 'configure' operation "
            "with the desired configuration payload."
        )

    def _load_device_configs(self, config_file: str, template_file=None) -> Dict[str, Any]:
        """
        Load and process device configurations from YAML file.

        If a template file is provided, the config file data is used as context
        to render the template, which should produce the final device_config structure.

        Args:
            config_file: Path to the YAML configuration file
            template_file: Optional path to user-defined Jinja2 template

        Returns:
            Dict mapping device names to their configuration data

        Raises:
            ConfigurationError: If file loading or parsing fails
        """
        # Load the config file (this already handles Jinja2 templating in the config file)
        config_data = self.render_config_file(config_file)

        if not config_data:
            return {}

        # If a user-defined template is provided, render it with config data
        if template_file:
            config_data = self._render_user_template(template_file, config_data)

        # Extract device_config section
        if "device_config" not in config_data:
            LOG.info("No 'device_config' section found in configuration file")
            return {}

        device_config_list = config_data["device_config"]
        if not isinstance(device_config_list, list):
            raise ConfigurationError("'device_config' must be a list of device configurations")

        # Convert list format to dict format
        device_configs = {}
        for device_entry in device_config_list:
            if isinstance(device_entry, dict):
                for device_name, config in device_entry.items():
                    device_configs[device_name] = config
            else:
                raise ConfigurationError(f"Invalid device_config entry format. Expected dict, got {type(device_entry)}")

        LOG.info("Loaded configuration for %d device(s)", len(device_configs))
        return device_configs

    def _render_user_template(self, template_file: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Render a user-defined Jinja2 template with the given context.

        Args:
            template_file: Path to the template file (relative to config_path or absolute)
            context: Context dictionary to use for template rendering

        Returns:
            Rendered template as parsed YAML/JSON

        Raises:
            ConfigurationError: If template rendering fails
        """
        import yaml

        # Resolve template file path
        if os.path.isabs(template_file):
            template_path = template_file
        else:
            # First check in config_path (for user-provided templates)
            template_path = os.path.normpath(os.path.join(self.config_utils.config_path, template_file))
            # If not found in config_path, check in template_path (for bundled templates)
            if not os.path.exists(template_path):
                template_path = os.path.normpath(os.path.join(self.config_utils.template_path, template_file))

        LOG.info("Rendering user template: %s", template_path)

        try:
            with open(template_path, "r") as f:
                template_content = f.read()

            template = Template(template_content)
            rendered_content = template.render(**context)

            # Parse as YAML (which also handles JSON)
            result = yaml.safe_load(rendered_content)
            LOG.debug("Template rendered successfully")
            return result

        except FileNotFoundError:
            raise ConfigurationError(f"User template file not found: {template_path}")
        except yaml.YAMLError as e:
            raise ConfigurationError(f"YAML parsing error after template rendering: {str(e)}")
        except Jinja2TemplateError as e:
            raise ConfigurationError(f"Jinja2 template error in '{template_path}': {str(e)}")

    def _parse_payload(self, config_data: Dict[str, Any], device_name: str) -> Optional[Dict[str, Any]]:
        """
        Parse the payload from device configuration.

        The payload can be:
        1. A string containing JSON (parsed from YAML multi-line string)
        2. A dict (already parsed YAML/JSON structure)

        Args:
            config_data: Configuration data for a device
            device_name: Device name for error reporting

        Returns:
            Parsed payload as a dictionary, or None if no payload

        Raises:
            ConfigurationError: If payload parsing fails
        """
        if config_data is None:
            return None

        payload = config_data.get("payload")
        if payload is None:
            LOG.warning("No 'payload' field found for device '%s'", device_name)
            return None

        # If payload is already a dict, return it
        if isinstance(payload, dict):
            LOG.debug("Payload for '%s' is already a dict", device_name)
            return payload

        # If payload is a string, try to parse as JSON
        if isinstance(payload, str):
            try:
                parsed_payload = json.loads(payload)
                LOG.debug("Successfully parsed JSON payload for '%s'", device_name)
                return parsed_payload
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid JSON payload for device '{device_name}': {str(e)}")

        raise ConfigurationError(
            f"Invalid payload type for device '{device_name}'. " f"Expected dict or JSON string, got {type(payload)}"
        )
