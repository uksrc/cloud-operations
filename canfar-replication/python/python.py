#!/usr/bin/env python3
"""
Label all artifacts in Harbor repositories with a label matching the
repository name. Labels are looked up globally (scope=g).
"""

import logging
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote
import hcl2
import requests
from requests.auth import HTTPBasicAuth

from config import PROJECTS

# ------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------

def load_tfvars(path: str) -> dict:
    with open(path) as f:
        return hcl2.load(f)

TFVARS = load_tfvars("../tf/variables.auto.tfvars")

HARBOR_URL = TFVARS["harbor_dest_url"].strip('"')
HARBOR_USER = TFVARS["primary_user"].strip('"')
HARBOR_PASS = TFVARS["primary_user_password"].strip('"')

PAGE_SIZE = 100
VERIFY_SSL = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("harbor-labeler")


@dataclass
class Stats:
    labeled: int = 0
    already_labeled: int = 0
    failed: int = 0
    skipped_repos: int = 0


class HarborClient:
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.verify = verify_ssl

        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _paginate(self, path: str, params: Optional[dict] = None):
        params = dict(params or {})
        page = 1
        while True:
            params["page"] = page
            params["page_size"] = PAGE_SIZE
            resp = self.session.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            yield from batch
            page += 1

    def get_repositories(self, project_name: str):
        yield from self._paginate(f"/api/v2.0/projects/{project_name}/repositories")

    def get_artifacts(self, project_name: str, repo_encoded: str):
        yield from self._paginate(
            f"/api/v2.0/projects/{project_name}/repositories/{repo_encoded}/artifacts"
        )

    def get_global_label_id(self, label_name: str) -> Optional[int]:
        resp = self.session.get(
            f"{self.base_url}/api/v2.0/labels",
            params={"scope": "g", "name": label_name},
        )
        resp.raise_for_status()
        results = resp.json()
        return results[0]["id"] if results else None

    def attach_label(self, project_name: str, repo_encoded: str, digest: str, label_id: int) -> int:
        resp = requests.post(
            f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{repo_encoded}/artifacts/{digest}/labels",
            json={"id": label_id},
            auth=HTTPBasicAuth(HARBOR_USER, HARBOR_PASS),
            verify=False,
        )
        return resp.status_code


def repo_short_name(full_name: str, project_name: str) -> str:
    """Strip the leading 'project/' prefix from a repository's full name."""
    prefix = f"{project_name}/"
    return full_name[len(prefix):] if full_name.startswith(prefix) else full_name


def main():
    client = HarborClient(HARBOR_URL, HARBOR_USER, HARBOR_PASS, verify_ssl=VERIFY_SSL)
    stats = Stats()

    # Cache label lookups since the same repo name might recur across projects
    label_cache: dict[str, Optional[int]] = {}

    def resolve_label(label_name: str) -> Optional[int]:
        if label_name not in label_cache:
            label_cache[label_name] = client.get_global_label_id(label_name)
        return label_cache[label_name]

    for project_name in PROJECTS:
        log.info("=== Project: %s ===", project_name)

        repos = list(client.get_repositories(project_name))
        if not repos:
            log.info("  No repositories found.")
            continue

        for repo in repos:
            repo_full_name = repo["name"]
            repo_name = repo_short_name(repo_full_name, project_name)
            repo_encoded = quote(repo_full_name.split("/", 1)[-1], safe="")

            log.info("  --- Repository: %s ---", repo_name)

            label_id = resolve_label(repo_name)
            if label_id is None:
                log.warning(
                    "    No matching global label named '%s', skipping.", repo_name
                )
                stats.skipped_repos += 1
                continue

            artifacts = list(client.get_artifacts(project_name, repo_encoded))
            if not artifacts:
                log.info("    No artifacts found.")
                continue

            for artifact in artifacts:
                digest = artifact["digest"]
                status = client.attach_label(project_name, repo_encoded, digest, label_id)

                if status == 200:
                    log.info("    OK: %s", digest)
                    stats.labeled += 1
                elif status == 409:
                    log.info("    Already labeled: %s", digest)
                    stats.already_labeled += 1
                else:
                    log.error("    FAILED (%s): %s", status, digest)
                    stats.failed += 1

    log.info(
        "Done. Labeled=%d, already_labeled=%d, failed=%d, skipped_repos=%d",
        stats.labeled, stats.already_labeled, stats.failed, stats.skipped_repos,
    )

    if stats.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()