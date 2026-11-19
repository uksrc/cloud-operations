#!/bin/sh
set -e

# Fail immediately if required password or SSH key file are missing
: "${HARBOR_PASSWORD:?Error: HARBOR_PASSWORD environment variable is not set}"

SSH_KEY_PATH="${SSH_KEY_PATH:-/etc/ssh-key/ssh-privatekey}"
if [ ! -f "$SSH_KEY_PATH" ]; then
 echo "Error: SSH private key not found at $SSH_KEY_PATH"
 exit 1
fi

HARBOR_URL="${HARBOR_URL:-https://harbor.ral.uksrc.org}"
HARBOR_USER="${HARBOR_USER:-admin}"
GIT_REPO_URL="${GIT_REPO_URL:-git@github.com:uksrc/cloud-operations.git}"
GIT_BRANCH="${GIT_BRANCH:-pog-209-harbor-backup}"

# Configure Git to use the mounted SSH deploy key without interactive host prompts
export GIT_SSH_COMMAND="ssh -i ${SSH_KEY_PATH} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

# Base directory (Defaults to /tmp in K8s/Docker, allows terminal/env override)
MOUNT_DIR="${MOUNT_DIR:-/tmp/harbor-backup-repo}"

# Subfolder path for JSON files inside the repository
CONFIG_DIR="harbor-configs/backups"

echo "=== Starting Harbor Backup Job ==="
mkdir -p "$MOUNT_DIR"
cd "$MOUNT_DIR"

if [ ! -d ".git" ]; then
  echo "Initializing repository in $MOUNT_DIR..."
  git init
  git remote add origin "$GIT_REPO_URL"
  git fetch origin
else
  echo "Updating existing repository in $MOUNT_DIR..."
  git fetch origin
fi

git config user.name "${GIT_USER_NAME:-harbor-backup-bot}"
git config user.email "${GIT_USER_EMAIL:-harbor-backup-bot@users.noreply.github.com}"

if git show-ref --verify --quiet "refs/heads/${GIT_BRANCH}"; then
  git checkout "$GIT_BRANCH"
  git pull origin "$GIT_BRANCH"
elif git show-ref --verify --quiet "refs/remotes/origin/${GIT_BRANCH}"; then
  git checkout -b "$GIT_BRANCH" "origin/${GIT_BRANCH}"
else
  git checkout -b "$GIT_BRANCH"
fi

mkdir -p "$CONFIG_DIR"

echo "Exporting projects..."
curl -sf -u "${HARBOR_USER}:${HARBOR_PASSWORD}" \
  "${HARBOR_URL}/api/v2.0/projects?page_size=100" | jq '.' > "${CONFIG_DIR}/projects.json"

echo "Exporting registries..."
curl -sf -u "${HARBOR_USER}:${HARBOR_PASSWORD}" \
  "${HARBOR_URL}/api/v2.0/registries?page_size=100" | jq '.' > "${CONFIG_DIR}/registries.json"

echo "Exporting replication policies..."
curl -sf -u "${HARBOR_USER}:${HARBOR_PASSWORD}" \
  "${HARBOR_URL}/api/v2.0/replication/policies?page_size=100" | jq '.' > "${CONFIG_DIR}/replication-policies.json"

echo "Exporting system info..."
curl -sf -u "${HARBOR_USER}:${HARBOR_PASSWORD}" \
  "${HARBOR_URL}/api/v2.0/systeminfo" | jq '.' > "${CONFIG_DIR}/harbor-systeminfo.json"

# Stage all files in harbor-configs/backups
git add -f "$CONFIG_DIR"

if git diff --staged --quiet; then
  echo "No changes detected in harbor-configs/backups. Skipping commit."
else
  git commit -m "chore(harbor): update harbor config backup $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  git push origin "$GIT_BRANCH"
  echo "Changes committed and pushed to branch ${GIT_BRANCH} successfully."
fi