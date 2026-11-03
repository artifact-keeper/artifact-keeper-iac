# demo.artifactkeeper.com

The public demo's deployment moved to its own repository,
[`artifact-keeper/artifact-keeper-demo`](https://github.com/artifact-keeper/artifact-keeper-demo)
(private). The compose file, seed data, Caddy config, systemd units and runbook live there. Make
changes to the demo in that repository.

The files that used to be in this directory are in this repository's git history. Don't reuse them:
the credentials they contain have been rotated, and their reset script destroys the demo's data.
