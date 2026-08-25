# Phase III compute-worker network policy

## Purpose and boundary

Phase III in-job tasks must not open internet sockets. Public PDB and AFDB
acquisition belongs to a separate bounded dispatcher stage that completes on
the login node before Slurm submission. The existing network labels select the
outer Nextflow controller rather than a child worker, but that controller is
itself inside a Slurm allocation and is not a login-network exception. A label
or proxy setting alone is not a denial boundary, so the Marmic and Viper
profiles use a separate process shell for every in-job Nextflow task.

The shell requires a numeric `SLURM_JOB_ID` and executes the task through the
fixed `/usr/bin/unshare` interface with a new user and network namespace. The
current worker UID/GID is retained inside the namespace so scientific tools do
not observe a false root identity. The namespace has no host network devices
or routes. It exports `GTD_COMPUTE_NETWORK_ACCESS=false` for retained command
diagnostics. Marmic `run_local` and Viper `needs_internet` retain their bounded
controller-local scheduling but do not override this shell or grant network
access.

## Inputs, outputs, and failure semantics

`bootstrap/nf-gtd-worker-offline-shell` receives only the arguments that
Nextflow would normally pass to `/bin/bash`. It writes no scientific output.
Its effective inputs are the exact source tree, site profile, Slurm allocation,
`/usr/bin/unshare`, and generated task script.

- Exit 78: the shell was reached without a numeric Slurm job context.
- Exit 69: the fixed namespace executable is absent or non-executable.
- Any `unshare` or task failure is returned unchanged and fails the task.
- There is no fallback to an ordinary shell and no environment switch that can
  enable compute networking.

Pre-submit login acquisition remains subject to the provider-plan, site,
execution-policy, database, and cache identities required by each provider
adapter. A configured-disabled or completed-no-hit provider remains a typed
scientific outcome and does not weaken this execution boundary. A profile that
has not staged every required network object before submission must fail rather
than ask an in-job controller task to fetch it.

The numeric Slurm marker is not treated as proof of ownership. Existing
terminal collection independently authenticates the run, site, profile,
scheduler job, source, and result before any remote evidence is accepted.

## Identity, qualification, and tests

The wrapper and both site configurations are tracked source-tree inputs. Phase
III task records also bind the exact source commit/tree and an execution-policy
digest while declaring `compute_network_access=false`; changing this policy
therefore changes the execution identity and prevents stale cross-policy reuse.

The focused repository regression checks the exact namespace command, rejects
an invocation outside numeric Slurm context before its payload, verifies both
site defaults, forbids an in-job ordinary-shell exception, and permits only the
three reviewed network-labelled modules. The complete Nextflow syntax and HPC
wrapper syntax checks pass locally. Before unknown pass 1, the selected
execution site must have one reviewed probe showing that an external socket
fails in both a child worker and controller-local task while bounded provider
staging succeeds before submission on the login node. Marmic is the current
target; Viper must be qualified only before running this scientific path there.
Until the Marmic record exists, `FCB-P1-15` is fixed locally but not qualified
for unknown pass 1.

## References

- [Nextflow process `shell` directive](https://www.nextflow.io/docs/latest/reference/process.html#shell)
  for the fixed interpreter command configured per process selector.
- [util-linux `unshare(1)` manual](https://man7.org/linux/man-pages/man1/unshare.1.html)
  for user and network namespace creation semantics.
