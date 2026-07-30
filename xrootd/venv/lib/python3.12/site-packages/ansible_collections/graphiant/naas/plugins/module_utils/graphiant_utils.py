"""
Graphiant Ansible Collection - Module Utilities

This module provides common utilities for Graphiant Ansible modules.
"""

import os
import sys
from typing import Any, Dict, Optional


def ansible_module_log(module: Any, message: str) -> None:
    """
    Emit a line through Ansible's module log hook when available (typically visible with -vvv
    and/or when ANSIBLE_LOG_PATH is set, depending on ansible-test / ansible version).

    Never raises: use for optional debug on failure paths and success checkpoints.
    """
    if module is None:
        return
    try:
        log = getattr(module, "log", None)
        if callable(log):
            log(f"[graphiant] {message}")
    except Exception:  # noqa: BLE001  # nosec B110
        pass  # best-effort logging; never raise into the caller


def graphiant_portal_auth_argument_spec():
    """
    Return the common argument_spec for Graphiant portal authentication.

    Use this in modules that connect to the Graphiant portal API so host, username,
    and password are defined in one place. Merge with module-specific args, for example:

        argument_spec = dict(
            **graphiant_portal_auth_argument_spec(),
            config_file=dict(type='str', required=True),
        )

    Authentication: provide O(access_token), or set the GRAPHIANT_ACCESS_TOKEN environment
    variable (e.g. after C(graphiant login) and C(source ~/.graphiant/env.sh)), or provide
    both O(username) and O(password).

    Returns:
        dict: Argument spec for host, username, password, access_token.
    """
    return {
        "host": dict(type="str", required=True, aliases=["base_url"]),
        "username": dict(type="str", required=False),
        "password": dict(type="str", required=False, no_log=True, default=None),
        "access_token": dict(type="str", required=False, no_log=True, default=None),
    }


def _resolved_access_token(module_params: Dict[str, Any]):
    """Prefer module access_token, then GRAPHIANT_ACCESS_TOKEN from the environment."""
    explicit = module_params.get("access_token")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    env_t = os.environ.get("GRAPHIANT_ACCESS_TOKEN")
    if env_t is not None and str(env_t).strip():
        return str(env_t).strip()
    return None


def _password_auth_usable(username, password) -> bool:
    if username is None or password is None:
        return False
    if not str(username).strip():
        return False
    if str(password) == "":
        return False
    return True


def _import_graphiant_libs():
    """
    Import Graphiant library modules.

    This function uses two import strategies:
    1. Ansible FQCN import: Required for Ansible modules so Ansible bundles the libs/ directory
    2. Direct import: Fallback for direct Python usage (e.g., test.py, scripts)

    Ansible traces FQCN imports to know what module_utils to bundle. Without FQCN,
    Ansible won't include the libs/ subdirectory in the module payload.

    IMPORTANT: We do NOT modify sys.path for the FQCN import case to avoid
    interfering with Ansible's own imports (which can cause sentinel module errors
    in ansible-core 2.19.x).

    Returns:
        tuple: (GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError)
        Returns (None, None, None, None, None) if imports fail (for ansible-test validate-modules)
    """
    # Strategy 1: Use Ansible FQCN import (required for Ansible module execution)
    # This tells Ansible to bundle the libs/ directory in the module payload
    # Do NOT modify sys.path here - let Ansible handle it
    try:
        from ansible_collections.graphiant.naas.plugins.module_utils.libs.graphiant_config import GraphiantConfig
        from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
            GraphiantPlaybookError,
            ConfigurationError,
            APIError,
            DeviceNotFoundError,
        )

        return GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
    except ImportError:
        pass

    # Strategy 2: Fallback for direct Python usage (e.g., test.py, scripts)
    # Only modify sys.path here, AFTER FQCN import failed
    # Use append instead of insert(0) to avoid interfering with other imports
    module_utils_dir = os.path.dirname(os.path.abspath(__file__))
    if module_utils_dir not in sys.path:
        sys.path.append(module_utils_dir)  # append, not insert(0)

    try:
        from .libs.graphiant_config import GraphiantConfig
        from .libs.exceptions import (
            APIError,
            ConfigurationError,
            DeviceNotFoundError,
            GraphiantPlaybookError,
        )

        return GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError
    except ImportError:
        # Return None values instead of raising to allow ansible-test validate-modules
        # to introspect the module even when dependencies are not available
        return None, None, None, None, None


# Import the Graphiant library modules lazily
# Use a function to get the imports so ansible-test validate-modules can introspect the module
# even when dependencies are not available
_GRAPHiant_LIBS_CACHE = None


def _get_graphiant_libs():
    """
    Get Graphiant library modules, importing them if necessary.

    This lazy import allows ansible-test validate-modules to introspect the module
    even when dependencies are not available.

    Returns:
        tuple: (GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError)
    """
    global _GRAPHiant_LIBS_CACHE
    if _GRAPHiant_LIBS_CACHE is None:
        _GRAPHiant_LIBS_CACHE = _import_graphiant_libs()
    return _GRAPHiant_LIBS_CACHE


# Re-exported for backward compatibility so callers can do:
#   from ...graphiant_utils import ConfigurationError
# _import_graphiant_libs() returns None for each name when the dependency is absent, allowing
# ansible-test validate-modules to introspect modules without the runtime library installed.
GraphiantConfig, GraphiantPlaybookError, ConfigurationError, APIError, DeviceNotFoundError = _import_graphiant_libs()

__all__ = [
    "GraphiantConfig",
    "GraphiantPlaybookError",
    "ConfigurationError",
    "APIError",
    "DeviceNotFoundError",
]


class GraphiantConnection:
    """
    Manages connection to Graphiant API and provides common functionality.
    """

    def __init__(
        self,
        host: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        access_token: Optional[str] = None,
        check_mode: bool = False,
    ):
        """
        Initialize Graphiant connection.

        Args:
            host: Graphiant API host URL
            username: Username for authentication (optional if access_token is used)
            password: Password for authentication (optional if access_token is used)
            access_token: Bearer token from CLI/SSO (optional if username/password are used)
            check_mode: If True, API write operations are skipped and payloads are only logged.
        """
        self.host = host
        self.username = username
        self.password = password
        self.access_token = access_token
        self.check_mode = check_mode
        self._graphiant_config = None

    @property
    def graphiant_config(self):
        """
        Get or create GraphiantConfig instance.

        Returns:
            GraphiantConfig: Graphiant configuration instance
        """
        # Lazy import to support ansible-test validate-modules
        graphiant_libs = _get_graphiant_libs()
        GraphiantConfig = graphiant_libs[0]
        GraphiantPlaybookError = graphiant_libs[1]

        if GraphiantConfig is None:
            raise ImportError(
                "Failed to import Graphiant libraries. "
                "Ensure the collection is properly installed and required dependencies are met."
            )

        if self._graphiant_config is None:
            try:
                self._graphiant_config = GraphiantConfig(
                    base_url=self.host,
                    username=self.username,
                    password=self.password,
                    check_mode=self.check_mode,
                    access_token=self.access_token,
                )
            except Exception as e:
                raise GraphiantPlaybookError(f"Failed to initialize Graphiant connection: {str(e)}")

        return self._graphiant_config

    def test_connection(self) -> bool:
        """
        Test the connection to Graphiant API.

        Returns:
            bool: True if connection is successful, False otherwise
        """
        try:
            # Try to get manager status to test connection
            status = self.graphiant_config.get_manager_status()
            return all(status.values())
        except Exception:
            return False


def get_graphiant_connection(module_params: Dict[str, Any], check_mode: bool = False) -> GraphiantConnection:
    """
    Create and return a Graphiant connection from module parameters.

    Args:
        module_params: Ansible module parameters
        check_mode: If True, API write operations (put_device_config, patch_global_config, etc.)
            are skipped and only the payload that would be sent is logged.

    Returns:
        GraphiantConnection: Initialized connection object
    """
    if "host" not in module_params or not module_params.get("host"):
        raise ValueError("Missing required parameter: host")

    token = _resolved_access_token(module_params)
    username = module_params.get("username")
    password = module_params.get("password")

    if token is None and not _password_auth_usable(username, password):
        raise ValueError(
            "Authentication requires GRAPHIANT_ACCESS_TOKEN (or module option access_token), "
            "or both username and password."
        )

    return GraphiantConnection(
        host=module_params["host"],
        username=username,
        password=password,
        access_token=token,
        check_mode=check_mode,
    )


def handle_graphiant_exception(exception: Exception, operation: str) -> str:
    """
    Handle Graphiant exceptions and return user-friendly error messages.

    Args:
        exception: The exception that occurred
        operation: Description of the operation that failed

    Returns:
        str: User-friendly error message
    """
    # Lazy import to support ansible-test validate-modules
    graphiant_libs = _get_graphiant_libs()
    GraphiantPlaybookError = graphiant_libs[1]
    ConfigurationError = graphiant_libs[2]
    APIError = graphiant_libs[3]
    DeviceNotFoundError = graphiant_libs[4]

    # If imports are not available, return a generic error message
    if ConfigurationError is None or APIError is None or DeviceNotFoundError is None or GraphiantPlaybookError is None:
        return f"Error during {operation}: {str(exception)}"

    if isinstance(exception, ConfigurationError):
        msg = str(exception)
        # Already a full sentence from portal/config loading (e.g. missing file path)
        if msg.startswith("Config file not found:"):
            return msg
        return f"Configuration error during {operation}: {msg}"
    elif isinstance(exception, APIError):
        return f"API error during {operation}: {str(exception)}"
    elif isinstance(exception, DeviceNotFoundError):
        return f"Device not found during {operation}: {str(exception)}"
    elif isinstance(exception, GraphiantPlaybookError):
        return f"Graphiant playbook error during {operation}: {str(exception)}"
    elif isinstance(exception, ValueError):
        return f"Invalid parameters for {operation}: {str(exception)}"
    elif isinstance(exception, (OSError, PermissionError, FileNotFoundError)):
        return f"File or I/O error during {operation}: {str(exception)}"
    elif isinstance(exception, ImportError):
        return f"Import error (missing optional dependency) during {operation}: {str(exception)}"
    elif isinstance(exception, (TypeError, KeyError, AttributeError)):
        return f"Internal error during {operation} ({type(exception).__name__}): {str(exception)}"
    else:
        return f"Unexpected error during {operation} ({type(exception).__name__}): {str(exception)}"
