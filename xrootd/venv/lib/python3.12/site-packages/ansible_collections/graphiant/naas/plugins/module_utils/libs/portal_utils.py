import os
from concurrent.futures import wait
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Optional

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from jinja2 import Template, TemplateError as Jinja2TemplateError

    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False
    TemplateError = Exception

from .logger import setup_logger
from .gcsdk_client import GraphiantPortalClient
from .exceptions import ConfigurationError

# Required dependencies - checked when functions are called
# Don't raise at module level to allow import test to pass

LOG = setup_logger()


class PortalUtils(object):

    def __init__(self, base_url=None, username=None, password=None, **kwargs):
        check_mode = kwargs.pop("check_mode", False)
        access_token = kwargs.pop("access_token", None)
        # Logs: Use current working directory (where playbook is run from)
        self.logs_path = os.path.join(os.getcwd(), "logs") + "/"  # Default logs path
        self.config_path = None
        self.template_path = None

        # Priority 1: Check user-configured environment variables (highest priority)
        configs_path = os.environ.get("GRAPHIANT_CONFIGS_PATH")
        if configs_path and os.path.exists(configs_path):
            LOG.info("PortalUtils : Using GRAPHIANT_CONFIGS_PATH: %s", configs_path)
            self.config_path = configs_path if configs_path.endswith("/") else configs_path + "/"

        templates_path = os.environ.get("GRAPHIANT_TEMPLATES_PATH")
        if templates_path and os.path.exists(templates_path):
            LOG.info("PortalUtils : Using GRAPHIANT_TEMPLATES_PATH: %s", templates_path)
            self.template_path = templates_path if templates_path.endswith("/") else templates_path + "/"

        # Priority 2: Find the collection root and set paths from there
        if not self.config_path or not self.template_path:
            collection_root = self._find_collection_root()
            if collection_root:
                LOG.info("PortalUtils : collection_root : %s", collection_root)
                if not self.config_path:
                    self.config_path = os.path.join(collection_root, "configs") + "/"
                if not self.template_path:
                    self.template_path = os.path.join(collection_root, "templates") + "/"

        # Priority 3: Fallback to the current working directory
        if not self.config_path:
            LOG.warning("PortalUtils : config_path not found, using current working directory: %s", os.getcwd())
            self.config_path = os.path.join(os.getcwd(), "configs") + "/"
        if not self.template_path:
            LOG.warning("PortalUtils : template_path not found, using current working directory: %s", os.getcwd())
            self.template_path = os.path.join(os.getcwd(), "templates") + "/"

        LOG.info("PortalUtils : config_path : %s", self.config_path)
        LOG.info("PortalUtils : template_path : %s", self.template_path)
        LOG.info("PortalUtils : logs_path : %s", self.logs_path)
        self.gsdk = GraphiantPortalClient(
            base_url=base_url,
            username=username,
            password=password,
            access_token=access_token,
            check_mode=check_mode,
        )
        self.gsdk.set_bearer_token()

    def _find_collection_root(self) -> Optional[str]:
        """
        Find the collection root directory (project root).

        The collection root is: ansible_collections/graphiant/naas/
        After Galaxy installation: ~/.ansible/collections/ansible_collections/graphiant/naas/

        This directory contains:
        - configs/ (user-provided configuration files)
        - templates/ (Jinja2 templates)
        - plugins/ (collection code including libs)
        - playbooks/ (example playbooks)

        Priority:
        1. Find the collection root based on common Ansible installation paths
        2. Walk up from current file location to find collection root (has plugins/module_utils/libs/)

        Returns:
            str: Path to the collection root directory
            None: If the collection root is not found
        """
        # Method 1: Find the collection root based on common Ansible installation paths
        # NOTE: We avoid importing ansible.constants here as it can cause issues inside AnsiballZ
        common_collection_paths = [
            os.path.expanduser("~/.ansible/collections"),
            "/usr/share/ansible/collections",
        ]
        for collections_path in common_collection_paths:
            if collections_path and os.path.exists(collections_path):
                collection_check = os.path.join(collections_path, "ansible_collections", "graphiant", "naas")
                if os.path.exists(collection_check):
                    LOG.info("Found graphiant collection root via common path: %s", collection_check)
                    return collection_check

        # Method 2: Walk up from current file location to find collection root
        # This file is at: .../plugins/module_utils/libs/portal_utils.py
        # Collection root is: .../ (3 levels up)
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        # Walk up: libs/ -> module_utils/ -> plugins/ -> collection_root/
        current_dir = current_file_dir
        for unused_level in range(4):  # Walk up 4 levels max  # pylint: disable=unused-variable
            # Check if this is the collection root (has plugins/module_utils/libs/)
            libs_check = os.path.join(current_dir, "plugins", "module_utils", "libs")
            if os.path.exists(libs_check):
                LOG.debug("Found collection root by walking up from file location: %s", current_dir)
                return current_dir
            # Also check if we're at the repo root (has ansible_collections/graphiant/naas/)
            collection_check = os.path.join(current_dir, "ansible_collections", "graphiant", "naas")
            if os.path.exists(collection_check):
                LOG.debug("Found collection root at repo root: %s", collection_check)
                return collection_check
            current_dir = os.path.dirname(current_dir)
            if current_dir == os.path.dirname(current_dir):  # Reached filesystem root
                break

        # Final fallback: Use current working directory
        # Users can create configs/ and templates/ in their working directory
        LOG.warning("Could not find collection root, using current working directory as fallback")
        return None

    def concurrent_task_execution(self, function, config_dict):
        """
        Executes a function concurrently using ThreadPoolExecutor for each key-value in config_dict.
        The value must be a dict of kwargs to pass to the function.

        :param function: Callable function to be executed concurrently
        :param config_dict: Dict with keys as identifiers and values as kwargs for the function
        :return: Dict with keys as original keys and values as Future objects
        """
        output_dict = {}
        with ThreadPoolExecutor(max_workers=150) as executor:
            for key, value in config_dict.items():
                output_dict[key] = executor.submit(function, **value)
            self.wait_checked(list(future for future in output_dict.values()))
        return output_dict

    @staticmethod
    def wait_checked(posible_futures):
        """
        Waits for a set of futures to complete, logging errors for those that fail.

        :param possible_futures: List of futures (may include None)
        """
        futures = [item for item in posible_futures if item is not None]
        LOG.debug("Waiting for futures %s to complete", futures)
        _done, not_done = wait(futures)

        if not_done:
            LOG.warning("%s futures did not finish running", len(not_done))
        failures = []
        for future in futures:
            try:
                if future:
                    future.result(timeout=0)
            except Exception as e:
                failures.append(e)
        if failures:
            raise Exception(f"futures failed: {failures}")

    def render_config_file(self, yaml_file):
        if not HAS_YAML:
            raise ImportError("PyYAML is required for this module. Install it with: pip install PyYAML")
        if not HAS_JINJA2:
            raise ImportError("Jinja2 is required for this module. Install it with: pip install Jinja2")
        """
        Load a YAML configuration file from the config path.
        Supports both regular YAML files and Jinja2-templated YAML files.

        Args:
            yaml_file (str): The filename of the YAML config (can be absolute or relative).

        Returns:
            dict: Parsed configuration data.

        Raises:
            ConfigurationError: If file cannot be read, Jinja2 rendering fails, or YAML parsing fails.
        """
        # Handle absolute paths
        if os.path.isabs(yaml_file):
            input_file_path = yaml_file
        else:
            # Handle relative paths by concatenating with config_path
            # Security: Normalize path to prevent path traversal attacks
            input_file_path = os.path.normpath(os.path.join(self.config_path, yaml_file))
            # Security: Validate that resolved path is within config_path to prevent path traversal
            config_path_real = os.path.realpath(self.config_path)
            input_file_path_real = os.path.realpath(input_file_path)
            if not input_file_path_real.startswith(config_path_real):
                raise ConfigurationError(
                    f"Security: Path traversal detected. File path '{yaml_file}' resolves outside config directory."
                )

        try:
            # Read the file content
            with open(input_file_path, "r") as file:
                file_content = file.read()

            # Try to render as Jinja2 template first (works for both templated and non-templated files)
            try:
                template = Template(file_content)
                rendered_content = template.render()
                LOG.debug("Successfully rendered Jinja2 template for '%s'", input_file_path)
            except Jinja2TemplateError as e:
                # If Jinja2 rendering fails, check if it's because of actual template syntax errors
                # or just because the file doesn't contain Jinja2 syntax
                # For now, we'll treat any Jinja2 error as a real error and raise it
                error_msg = f"Jinja2 template error in '{input_file_path}': {str(e)}"
                LOG.error(error_msg)
                raise ConfigurationError(error_msg) from e
            except Exception as e:
                # For other exceptions during rendering, log and re-raise
                error_msg = f"Error rendering Jinja2 template in '{input_file_path}': {str(e)}"
                LOG.error(error_msg)
                raise ConfigurationError(error_msg) from e

            # Parse the rendered YAML content
            config_data = yaml.safe_load(rendered_content)
            return config_data

        except FileNotFoundError:
            if os.path.isabs(yaml_file):
                error_msg = f"Config file not found: {input_file_path} (this absolute path does not exist)."
            else:
                error_msg = (
                    f"Config file not found: {input_file_path} "
                    f"(requested as {yaml_file!r}, resolved under the collection config directory; "
                    f"see environment variable GRAPHIANT_CONFIGS_PATH if needed). "
                    f"Check spelling, path, and file extension (.yaml vs .yml)."
                )
            LOG.error(error_msg)
            raise ConfigurationError(error_msg)
        except yaml.YAMLError as e:
            # Provide user-friendly YAML error messages
            if hasattr(e, "problem_mark"):
                line_num = e.problem_mark.line + 1
                col_num = e.problem_mark.column + 1
                error_msg = f"YAML syntax error in '{input_file_path}' at line {line_num}, column {col_num}:\n"
                error_msg += f"  {str(e)}\n"
                error_msg += (
                    f"Please check the YAML syntax around line {line_num} "
                    "and fix any indentation or formatting issues."
                )
                raise ConfigurationError(error_msg)
            else:
                raise ConfigurationError(f"YAML parsing error in '{input_file_path}': {str(e)}")
        except ConfigurationError:
            # Re-raise ConfigurationError as-is
            raise
        except Exception as e:
            error_msg = f"Error reading configuration file '{input_file_path}': {str(e)}"
            LOG.error(error_msg)
            raise ConfigurationError(error_msg) from e
