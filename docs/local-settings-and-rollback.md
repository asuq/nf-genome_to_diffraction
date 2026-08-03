# Local settings, removal, and restoration

## Scope

The repository does not modify shell startup files, global Git configuration,
system Python, or the global Pixi installation. The local integration work uses
only these user-controlled locations:

- `~/.local/bin/nf-gtd-hpc-test`: reviewed immutable HPC controller;
- `~/.config/nf-gtd-hpc-test/config.json`: host alias and local/remote paths;
- `REPOSITORY/.untracked/hpc-test/`: owner capabilities and collected run data;
- `~/.local/opt/phenix-current`: local selected-Phenix symlink;
- `~/.local/opt/phenix-2.1-6048/`: licensed local Phenix installation;
- `~/.local/share/nf-genome_to_diffraction/phenix/`: local Phenix manifests and
  verification/install logs; and
- Codex persistent command approvals for the installed controller's narrow
  routine operations.

Pixi being available on `PATH` was an operator installation, not a repository
setting. Do not remove it as part of this rollback unless that separate
installation is intentionally being retired.

## Disable without deleting evidence

Use a dated, user-owned backup directory so reversal remains recoverable. Replace
`YYYYMMDD` literally before running the commands:

```bash
export NF_GTD_ROLLBACK="$HOME/.local/state/nf-gtd-rollback/YYYYMMDD"
mkdir -p "$NF_GTD_ROLLBACK/bin" "$NF_GTD_ROLLBACK/config" \
  "$NF_GTD_ROLLBACK/phenix"

if test -e "$HOME/.local/bin/nf-gtd-hpc-test"; then
  mv "$HOME/.local/bin/nf-gtd-hpc-test" "$NF_GTD_ROLLBACK/bin/"
fi
if test -e "$HOME/.config/nf-gtd-hpc-test"; then
  mv "$HOME/.config/nf-gtd-hpc-test" "$NF_GTD_ROLLBACK/config/"
fi
if test -L "$HOME/.local/opt/phenix-current"; then
  mv "$HOME/.local/opt/phenix-current" "$NF_GTD_ROLLBACK/phenix/"
fi
```

This disables the controller and the selected Phenix link without deleting the
large licensed prefix, run evidence, or logs. In Codex settings, remove only the
persistent rules whose executable is the absolute installed
`nf-gtd-hpc-test` path. Confirm that a routine wrapper command prompts again.
There is no repository command that edits Codex's approval store.

The ignored `REPOSITORY/.untracked/hpc-test/` records contain the owner tokens
needed to query, collect, cancel, or clean existing managed runs. Preserve them
until all remote jobs are terminal and their evidence has been collected. If
they must be retired later, move the whole `hpc-test` directory into the dated
rollback directory; do not delete individual capability records and assume they
can be regenerated.

## Optional full local Phenix retirement

Only after confirming the licensed installation is no longer needed, move its
versioned prefix and evidence rather than deleting them immediately:

```bash
if test -d "$HOME/.local/opt/phenix-2.1-6048"; then
  mv "$HOME/.local/opt/phenix-2.1-6048" "$NF_GTD_ROLLBACK/phenix/"
fi
if test -d "$HOME/.local/share/nf-genome_to_diffraction/phenix"; then
  mv "$HOME/.local/share/nf-genome_to_diffraction/phenix" \
    "$NF_GTD_ROLLBACK/phenix/evidence"
fi
```

Moving or deleting the prefix invalidates manifests that record its absolute
path. Never substitute those stale manifests into a pipeline run.

## Restore

Restore the controller configuration and Phenix prefix to the same absolute
paths, then re-verify rather than trusting the backup alone:

```bash
mkdir -p "$HOME/.local/bin" "$HOME/.config" "$HOME/.local/opt" \
  "$HOME/.local/share/nf-genome_to_diffraction"
mv "$NF_GTD_ROLLBACK/bin/nf-gtd-hpc-test" "$HOME/.local/bin/"
mv "$NF_GTD_ROLLBACK/config/nf-gtd-hpc-test" "$HOME/.config/"
```

If Phenix was fully retired, move the versioned prefix and evidence back before
recreating `phenix-current`. Run the tracked Phenix verifier against the restored
manifest and require all seven commands to pass. Rebuild, checksum, and reinstall
the HPC controller from an immutable reviewed commit if its checksum no longer
matches the recorded value. Add back only the routine Codex approval pattern
documented in the [HPC feedback-loop runbook](hpc-feedback-loop.md#cleanup-and-codex-approval);
keep database start, raw SSH, scheduler commands, and cleanup approval-gated.

## Remote settings are separate

The Marmic bare mirror, `_tooling`, `_config`, `_cache`, `_locks`, `runs`, large
database roots, and licensed Linux Phenix prefix are remote state. Moving local
files does not remove them. Use owned wrapper status/collection first, then an
explicitly reviewed remote retirement procedure; never infer authority to erase
remote shared resources from this local rollback.
