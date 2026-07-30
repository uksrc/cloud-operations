"""
Centralized version management for Graphiant Playbooks Ansible Collection.

This file contains all version information for the collection and its dependencies.
All version references throughout the repository should use values from this file.
"""

# Collection version (semantic versioning: MAJOR.MINOR.PATCH)
__version__ = "26.6.0"
COLLECTION_VERSION = __version__

# Dependency versions
DEPENDENCIES = {
    # Core Python dependencies
    "PyYAML": "6.0.1",
    "Jinja2": "3.1.6",
    "tabulate": "0.9.0",

    # Graphiant SDK (use version >= 26.6.0)
    "graphiant-sdk": "26.6.0",

    # Ansible
    "ansible-core": ">=2.17.0",

    # Development dependencies
    "flake8": "7.3.0",
    "pylint": "3.3.7",
    "djlint": "1.34.0",
    "ansible-lint": ">=24.0.0",
    "pre-commit": "4.2.0",
    "antsibull-docs": ">=2.0.0,<3.0.0",
    "sphinx-ansible-theme": ">=0.9.0",
}

# Collection dependencies (for galaxy.yml)
COLLECTION_DEPENDENCIES = {
    "ansible.posix": ">=1.5.0",
}

# Python version requirement
# Compatible with ansible-core 2.17, 2.18, 2.19, and 2.20 (all support Python 3.7+)
REQUIRES_PYTHON = ">=3.7"

# Module version_added (should match collection version, but use major.minor format)
# Ansible requires version_added to be major.minor, not patch level
MODULE_VERSION_ADDED = "26.6.0"  # Derived from COLLECTION_VERSION (MAJOR.MINOR)
