# Harbor Replication Backup

This directory contains backups of Harbor replication configuration exported using the Harbor REST API v2.0.

## Files

| File | Description |
|--------|-------------|
| `registries.json` | Registry endpoint definitions |
| `replication-policies.json` | Replication policies |
| `harbor-systeminfo.json` | Harbor version information (optional) |

## Updating the Backups

> **Note:** These backups are generated using the Harbor API v2.0 endpoints:
>
> - `/api/v2.0/registries`
> - `/api/v2.0/replication/policies`
> - `/api/v2.0/systeminfo`
>
> If Harbor is upgraded, verify that these endpoints and response formats remain compatible.

Export registries:

```bash
curl -s -u admin:<password> \
  "https://<harbor>/api/v2.0/registries?page_size=100" \
  | jq '.' > registries.json
```

Export replication policies:

```bash
curl -s -u admin:<password> \
  "https://<harbor>/api/v2.0/replication/policies?page_size=100" \
  | jq '.' > replication-policies.json
```

(Optional) Export Harbor version information:

```bash
curl -s -u admin:<password> \
  "https://<harbor>/api/v2.0/systeminfo" \
  | jq '.' > harbor-systeminfo.json
```

Verify the counts match the Harbor UI:

```bash
jq length registries.json
jq length replication-policies.json
```

Commit updated backup files to Git.

## Restore Notes

- Registry credentials are not exported by Harbor.
- Registry credentials are stored in the SKAO 1Password vault.
- Registry endpoints must be recreated before replication policies can be restored.

## Validation

The restore process has been tested using Harbor deployed to a Kind cluster via Helm.

Validated steps:

- Export registry definitions
- Export replication policies
- Restore registry definitions into a clean Harbor instance
- Verify recreated registries in the Harbor UI