"""
Logging decorator for Ansible modules to capture detailed library logs
"""

import logging
import io
import functools


def _import_setup_logger():
    """
    Import setup_logger from libs.logger using the same pattern as _import_graphiant_libs.

    This function uses two import strategies:
    1. Ansible FQCN import: Required for Ansible modules so Ansible bundles the libs/ directory
    2. Direct import: Fallback for direct Python usage (e.g., test.py, scripts)

    Returns:
        function: setup_logger function from libs.logger
    """
    # Strategy 1: Use Ansible FQCN import (required for Ansible module execution)
    try:
        from ansible_collections.graphiant.naas.plugins.module_utils.libs.logger import setup_logger

        return setup_logger
    except ImportError:
        pass

    # Strategy 2: package-relative import (e.g. unit tests with PYTHONPATH at collection root)
    try:
        from .libs.logger import setup_logger

        return setup_logger
    except ImportError:
        return None


# Import setup_logger at module load time
_setup_logger = _import_setup_logger()


def capture_library_logs(func):
    """
    Decorator to capture and return detailed library logs for Ansible modules.

    This decorator:
    1. Captures all INFO level logs from the library
    2. Appends them to the result message if detailed logging is enabled
    3. Can be controlled via module parameter 'detailed_logs'

    Usage:
        @capture_library_logs
        def some_operation(module, *args, **kwargs):
            # Your operation code here
            pass
    """

    @functools.wraps(func)
    def wrapper(module, *args, **kwargs):
        # Check if detailed logging is enabled
        detailed_logs = module.params.get("detailed_logs", False)

        if not detailed_logs:
            # If detailed logging is disabled, just run the function normally
            return func(module, *args, **kwargs)

        # Note: ansible-playbook with detailed_logs: true embeds newlines in result_msg.
        # For best output formatting with detailed_logs, set ANSIBLE_STDOUT_CALLBACK=debug:
        # export ANSIBLE_STDOUT_CALLBACK=debug
        # This ensures clean output without literal \n characters

        # The debug task should pass msg as a multiline string (e.g. msg: |), not a list of
        # strings, or the callback may show literal \n in a one-line list repr. Callback
        # (default vs ANSIBLE_STDOUT_CALLBACK=debug) does not change that list behavior.

        # Set up logging capture
        log_capture = io.StringIO()

        # Custom handler that writes to our buffer
        class LogCaptureHandler(logging.Handler):
            def __init__(self, buffer):
                super().__init__()
                self.buffer = buffer

            def emit(self, record):
                self.buffer.write(self.format(record) + "\n")

        # Create and configure the handler
        log_handler = LogCaptureHandler(log_capture)
        log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        log_handler.setFormatter(formatter)

        # Get the library logger using imported setup_logger (same as libs/logger.py)
        # This ensures we get the same logger instance used by the library
        if _setup_logger:
            LOG = _setup_logger()
        else:
            # Fallback to getting logger by name if import failed
            LOG = logging.getLogger("Graphiant_playbook")
        LOG.addHandler(log_handler)
        log_handler_added = True

        try:
            # Execute the original function
            result = func(module, *args, **kwargs)

            # Capture the logs
            captured_logs = log_capture.getvalue()
            if captured_logs and "result_msg" in result:
                result["result_msg"] += f"\n\nDetailed logs:\n{captured_logs}"

            return result

        except Exception as e:
            if "Config file not found" in str(e):
                raise
            # Capture logs even when exception occurs
            captured_logs = log_capture.getvalue()
            if captured_logs:
                # Add logs to the exception message for better debugging
                enhanced_message = f"{str(e)}\n\nDetailed logs before exception:\n{captured_logs}"
                # Create a new exception with enhanced message
                new_exception = type(e)(enhanced_message)
                new_exception.__cause__ = e
                raise new_exception
            raise

        finally:
            # Clean up the handler
            if log_handler_added:
                try:
                    LOG.removeHandler(log_handler)
                except Exception:  # noqa: BLE001  # nosec B110
                    pass  # best-effort cleanup; ignore handler removal errors
                log_capture.close()

    return wrapper
