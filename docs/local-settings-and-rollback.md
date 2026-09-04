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

Before replacing the installed controller, preserve the prior mode-`0555`
binary under `REPOSITORY/.untracked/install-backups/` with a checksum-derived
suffix. Verify the newly built and installed files have the same SHA-256. To
roll back that upgrade, install the preserved binary back to the same absolute
path with mode `0555`, then verify its recorded checksum before use.

Pixi being available on `PATH` was an operator installation, not a repository
setting. Do not remove it as part of this rollback unless that separate
installation is intentionally being retired.

The active controller configuration names the stable SSH alias `viper-cpu` and
records `site_id=viper-cpu`. Preserve the former Marmic configuration separately;
legacy records without a site ID are Marmic-only. The selected endpoint remains
an operator setting in `~/.ssh/config`. To change login nodes,
preserve the previous `Host marmic` block in the dated rollback directory and
change only its `HostName`. Do not put the concrete site hostname into the
tracked controller configuration or grant a second raw-SSH approval. Restore
the former node by restoring the saved block, leaving the controller
configuration and owned run capabilities unchanged. The installed controller's
routine remote-operation margin is compiled into its reviewed zipapp; restoring
an older backed-up controller also restores that version's shorter margin.

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
The recoverable `database-archive-failed` operation is also excluded from
persistent approval because it mutates retained remote evidence from a reviewed
failed or cancelled run.

## Remote settings are separate

Viper's `/ptmp` run root, user tool/configuration directory, bare mirror,
databases, caches, and licensed Phenix prefix are remote state. Marmic
equivalents remain historical remote state. Moving local files does not remove
either site's evidence. The tracked [Viper runbook](viper-cpu-runbook.md)
describes how to disable active settings without deleting them.

The Marmic bare mirror, `_tooling`, `_config`, `_cache`, `_locks`, `runs`, large
database roots, and licensed Linux Phenix prefix are remote state. Moving local
files does not remove them. Use owned wrapper status/collection first, then an
explicitly reviewed remote retirement procedure; never infer authority to erase
remote shared resources from this local rollback.

The `p0-configure` operation creates an absent `_config/p0.paths` below the
configured Marmic run root. A reviewed replacement additionally requires the
exact current checksum through `--replace-current-sha256`. Rotation is refused
while any run that records the current checksum is nonterminal, retains the
old payload as `p0.paths.retired-<SHA256>`, and verifies the replacement after
its atomic publication. Record both checksums in the ignored qualification
dossier. No raw SSH or direct remote file edit is part of configuration
rotation. Require `nf-gtd-hpc-test readiness p0` to report `ready=true` before
staging another run.

Before configuration, the separately approved `p0-inputs-stage` operation adds
one content-addressed, read-only directory below the dispatcher root's fixed
`_p0_inputs/` directory. It also uses the local private files
`.untracked/m0-qualification/p0-inputs.json` (operator-prepared specification)
and `.untracked/m0-qualification/hpc-p0.paths` (generated seven-line candidate).
The wrapper accepts no destination path. Replacing a different local candidate
requires its exact checksum through `--replace-current-paths-sha256`; the prior
mode-`0600` file is retained as `hpc-p0.paths.retired-<SHA256>`.

To undo the local settings, remove only those two exact files after saving any
desired checksum record. They are ignored by Git, so this does not alter the
repository. Restore a retained P0 configuration only through the same
checksum-gated rotation operation; the nonterminal-run guard still applies.
The immutable `_p0_inputs/p0i_<SHA256>` directory may be retained for
reproducibility; removing it is a separate destructive cleanup requiring an
exact resolved target, ownership checks, explicit approval, and confirmation
that no retained run references its ID. Routine `clean` removes only a run
directory and never removes P0 configuration or input bundles.
