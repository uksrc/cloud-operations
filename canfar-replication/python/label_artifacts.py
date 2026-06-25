#!/usr/bin/env python3
"""
Reads labels from artifacts in a source Harbor registry and applies
matching labels to the same artifacts in a destination Harbor registry,
matched by digest.
"""

import logging
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote
from http.cookiejar import CookieJar
import hcl2
import requests
from requests.auth import HTTPBasicAuth

from config import PROJECTS

def load_tfvars(path: str) -> dict:
    with open(path) as f:
        return hcl2.load(f)

TFVARS = load_tfvars("../tf/variables.auto.tfvars")

HARBOR_URL = TFVARS["harbor_dest_url"].strip('"')
HARBOR_USER = TFVARS["primary_user"].strip('"')
HARBOR_PASS = TFVARS["primary_user_password"].strip('"')
HARBOR_REMOTE_URL = TFVARS["remote_harbor_url"].strip('"')

PAGE_SIZE = 100
VERIFY_SSL = False
SOURCE_VERIFY_SSL = True

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
    skipped_artifacts: int = 0


class BlockAllCookies(CookieJar):
    def set_cookie(self, cookie):
        pass


class HarborClient:
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.cookies = BlockAllCookies()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.verify = verify_ssl

        if username and password:
            self.session.auth = HTTPBasicAuth(username, password)

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
            f"/api/v2.0/projects/{project_name}/repositories/{repo_encoded}/artifacts",
            params={"with_label": "true"},
        )

    def get_global_label_id(self, label_name: str) -> Optional[int]:
        resp = self.session.get(
            f"{self.base_url}/api/v2.0/labels",
            params={"scope": "g", "name": label_name},
        )
        resp.raise_for_status()
        results = resp.json()
        return results[0]["id"] if results else None

    def attach_label(self, project_name: str, repo_encoded: str, digest: str, label_id: int) -> tuple[int, str]:
        resp = self.session.post(
            f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{repo_encoded}/artifacts/{digest}/labels",
            json={"id": label_id},
        )
        return resp.status_code, resp.text


def repo_short_name(full_name: str, project_name: str) -> str:
    prefix = f"{project_name}/"
    return full_name[len(prefix):] if full_name.startswith(prefix) else full_name


def main():
    source = HarborClient(HARBOR_REMOTE_URL, SOURCE_VERIFY_SSL)
    dest = HarborClient(HARBOR_URL, HARBOR_USER, HARBOR_PASS, VERIFY_SSL)
    stats = Stats()

    # Cache destination label lookups to avoid redundant API calls
    label_cache: dict[str, Optional[int]] = {}

    def resolve_dest_label_id(label_name: str) -> Optional[int]:
        if label_name not in label_cache:
            label_cache[label_name] = dest.get_global_label_id(label_name)
        return label_cache[label_name]

    for project_name in PROJECTS:
        log.info("=== Project: %s ===", project_name)

        repos = list(dest.get_repositories(project_name))
        if not repos:
            log.info("  No repositories found.")
            continue

        for repo in repos:
            repo_full_name = repo["name"]
            repo_name = repo_short_name(repo_full_name, project_name)
            repo_encoded = quote(repo_full_name.split("/", 1)[-1], safe="")

            log.info("  --- Repository: %s ---", repo_name)

            # Get artifacts from source (carries label metadata)
            try:
                source_artifacts = {
                    a["digest"]: a
                    for a in source.get_artifacts(project_name, repo_encoded)
                }
            except requests.HTTPError as e:
                log.warning("    Could not fetch from source (%s), skipping.", e)
                stats.skipped_repos += 1
                continue

            # Get artifacts from destination
            dest_artifacts = list(dest.get_artifacts(project_name, repo_encoded))
            if not dest_artifacts:
                log.info("    No artifacts found in destination.")
                continue

            for artifact in dest_artifacts:
                digest = artifact["digest"]

                # Match by digest to find the same artifact in source
                source_artifact = source_artifacts.get(digest)
                if not source_artifact:
                    log.warning("    No matching source artifact for %s, skipping.", digest)
                    stats.skipped_artifacts += 1
                    continue

                # Read labels from source artifact
                source_labels = source_artifact.get("labels") or []
                if not source_labels:
                    log.info("    No labels on source artifact %s, skipping.", digest)
                    stats.skipped_artifacts += 1
                    continue

                for source_label in source_labels:
                    label_name = source_label["name"]

                    # Resolve label ID in destination registry
                    label_id = resolve_dest_label_id(label_name)
                    if label_id is None:
                        log.warning(
                            "    Label '%s' not found in destination registry, skipping.",
                            label_name,
                        )
                        continue

                    status, body = dest.attach_label(project_name, repo_encoded, digest, label_id)

                    if status == 200:
                        log.info("    OK [%s]: %s", label_name, digest)
                        stats.labeled += 1
                    elif status == 409:
                        log.info("    Already labeled [%s]: %s", label_name, digest)
                        stats.already_labeled += 1
                    else:
                        log.error("    FAILED (%s) [%s]: %s — %s", status, label_name, digest, body)
                        stats.failed += 1

    log.info(
        "Done. Labeled=%d, already_labeled=%d, failed=%d, skipped_repos=%d, skipped_artifacts=%d",
        stats.labeled, stats.already_labeled, stats.failed, stats.skipped_repos, stats.skipped_artifacts,
    )

    if stats.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
