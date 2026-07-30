"""
Base manager class for Graphiant Playbooks.

This module provides a base class that contains common functionality
for all configuration managers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional
from .config_utils import ConfigUtils
from .logger import setup_logger
from .exceptions import ConfigurationError, APIError, DeviceNotFoundError, SiteNotFoundError

LOG = setup_logger()


class BaseManager(ABC):
    """
    Base class for all configuration managers.

    Provides common functionality for configuration processing,
    template rendering, and API communication.
    """

    def __init__(self, config_utils: ConfigUtils):
        """
        Initialize the base manager.

        Args:
            config_utils: Instance of ConfigUtils containing common utilities
        """
        self.config_utils = config_utils
        self.gsdk = config_utils.gsdk
        self.template = config_utils.template

    @abstractmethod
    def configure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Configure resources based on the provided YAML file.

        Args:
            config_yaml_file: Path to the YAML configuration file
        """
        pass

    @abstractmethod
    def deconfigure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Deconfigure resources based on the provided YAML file.

        Args:
            config_yaml_file: Path to the YAML configuration file
        """
        pass

    def render_config_file(self, yaml_file: str) -> Dict[str, Any]:
        """
        Load and parse a YAML configuration file.

        Args:
            yaml_file: Path to the YAML configuration file

        Returns:
            Parsed configuration data

        Raises:
            ConfigurationError: If the file cannot be loaded or parsed
        """
        try:
            config_data = self.config_utils.render_config_file(yaml_file)
            if config_data is None:
                raise ConfigurationError(f"Failed to load configuration file: {yaml_file}")
            return config_data
        except ConfigurationError:
            # Preserve concise messages (e.g. file not found) from ConfigUtils/portal_utils
            raise
        except Exception as e:
            LOG.error("Error rendering configuration file %s: %s", yaml_file, str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            import traceback

            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"Error rendering configuration file {yaml_file}: {str(e)}")

    def execute_concurrent_tasks(self, function, config_dict: Mapping[Any, Any]) -> Dict[str, Any]:
        """
        Execute a function concurrently for each item in the config dictionary.

        Args:
            function: The function to execute
            config_dict: Dictionary with configuration data

        Returns:
            Dictionary with execution results
        """
        try:
            return self.config_utils.concurrent_task_execution(function, config_dict)
        except Exception as e:
            raise APIError(f"Error executing concurrent tasks: {str(e)}")

    def get_device_id(self, device_name: str) -> Optional[int]:
        """
        Get device ID by device name.

        Args:
            device_name: Name of the device

        Returns:
            Device ID if found, None otherwise

        Raises:
            DeviceNotFoundError: If device cannot be found
        """
        device_id = self.gsdk.get_device_id(device_name)
        if not device_id:
            raise DeviceNotFoundError(f"Device '{device_name}' not found")
        return device_id

    def get_site_id(self, site_name: str) -> Optional[int]:
        """
        Get site ID by site name.

        Args:
            site_name: Name of the site

        Returns:
            Site ID if found, None otherwise

        Raises:
            SiteNotFoundError: If site cannot be found
        """
        site_id = self.gsdk.get_site_id(site_name)
        if not site_id:
            raise SiteNotFoundError(f"Site '{site_name}' not found")
        return site_id
