#!/usr/bin/env bash
# Vault password from environment (no plaintext password file).
# Usage:
#   export ANSIBLE_VAULT_PASSPHRASE='your-vault-passphrase'
#   export ANSIBLE_VAULT_PASSWORD_FILE=/path/to/this/script
#   ansible-playbook ... (or run tests that use vault)
# See: https://forum.ansible.com/t/environment-variable-as-vault-key/40837
echo "${ANSIBLE_VAULT_PASSPHRASE}"
