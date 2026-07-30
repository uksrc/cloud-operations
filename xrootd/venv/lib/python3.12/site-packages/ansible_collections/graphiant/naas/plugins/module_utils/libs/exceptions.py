"""
Custom exceptions for Graphiant Playbooks.

This module defines custom exceptions to provide better error handling
and more specific error messages for different failure scenarios.
"""


class GraphiantPlaybookError(Exception):
    """Base exception for all Graphiant Playbook errors."""

    pass


class ConfigurationError(GraphiantPlaybookError):
    """Raised when there's an error in configuration processing."""

    pass


class TemplateError(GraphiantPlaybookError):
    """Raised when there's an error in template rendering."""

    pass


class APIError(GraphiantPlaybookError):
    """Raised when there's an error in API communication."""

    pass


class DeviceNotFoundError(GraphiantPlaybookError):
    """Raised when a device cannot be found."""

    pass


class SiteNotFoundError(GraphiantPlaybookError):
    """Raised when a site cannot be found."""

    pass


class ValidationError(GraphiantPlaybookError):
    """Raised when input validation fails."""

    pass
