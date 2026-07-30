# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):
    """Documentation fragment for Graphiant portal authentication options shared by all modules."""

    DOCUMENTATION = r"""
options:
  host:
    description:
      - Graphiant portal host URL for API connectivity.
      - 'Example: "https://api.graphiant.com"'
    type: str
    required: true
    aliases: [ base_url ]
  access_token:
    description:
      - Bearer token for API authentication (for example, from C(graphiant login), which opens a
        browser for sign-in (SSO or non-SSO) and retrieves the token).
      - If not passed as a module argument, the collection reads C(GRAPHIANT_ACCESS_TOKEN)
        (set after C(graphiant login) when you C(source ~/.graphiant/env.sh)).
      - When a bearer token is present (module argument or environment), it takes precedence over
        O(username) and O(password).
      - If no valid token is available, the module authenticates with O(username) and O(password)
        when both are supplied.
    type: str
    required: false
  username:
    description:
      - Graphiant portal username for authentication.
      - Required for password-based login when no valid bearer token is available from
        O(access_token) or C(GRAPHIANT_ACCESS_TOKEN).
    type: str
    required: false
  password:
    description:
      - Graphiant portal password for authentication.
      - Required for password-based login when no valid bearer token is available from
        O(access_token) or C(GRAPHIANT_ACCESS_TOKEN).
    type: str
    required: false
"""
