# Dynamic, resolution-aware Matthews priors

## Purpose and claim boundary

The Matthews stage estimates which single-component `ASU = nA` copy states
are physically credible for one catalogue sequence and one diffraction data
set. It does not identify the protein, establish oligomeric state, or prove that
the asymmetric unit is homogeneous. Every score remains a soft ordering prior;
low or zero prior never removes a physically possible state.

The active backend is
`mattprob_kde_2013_resolution_cumulative_pn_v1`. It has two independently
visible factors:

1. a resolution-conditioned empirical solvent-fraction density; and
2. the published empirical frequency `P(n)` of homooligomer copy counts in the
   asymmetric unit.

Their product is a review-ordering weight, not a calibrated probability of
protein identity. The unweighted solvent density and copy-frequency factor are
published in every current Matthews row and MR review. The MR review also
publishes an independent MR rank so disagreement
cannot be hidden in one unexplained score.

## Reference and method

The bundled identifier-free reference is derived from the protein table in the
official `kernel_data_tables_2013.zip` MATTPROB download:

- source archive SHA-256:
  `232dd75da88abb1990be1dd20f71d56ea54193d252166d6df6efca57ba62c031`;
- source protein member SHA-256:
  `3432ae0a2b4771e17a3cc2b8eec63999cabdfe0d3cacb16bc2bd5c485f5c30d0`;
- bundled resource SHA-256:
  `4114691d739f79ade662dc9ee1df5bd5f0e89c0499d1175337c7295b0191d906`;
- 60,194 usable resolution/solvent pairs from 60,218 source rows; and
- 50,190 positive homooligomer-copy observations over 30 distinct copy counts.

For a query high-resolution limit, the estimator follows the published
cumulative convention and uses reference structures whose reported resolution
is at least as good. A deterministic Gaussian binned kernel-density estimate
uses the `KernSmooth::bkde` oversmoothed bandwidth formula and is scaled so its
maximum is one. The single-component prior for copy state `n` is:

```text
relative solvent density(Vs | resolution) * empirical P(n)
```

The generic `P(n)` factor is deliberately used here because the operator asked
that very-high-copy small-protein hypotheses no longer dominate the unknown
single-component screen. Weichenberger and Rupp describe this weighting as a
possible generic prior and caution that stronger experimental knowledge of the
biological assembly should override it. No such assembly prior is inferred by
this workflow.

References:

- C. X. Weichenberger and B. Rupp, “Ten years of probabilistic estimates of
  biocrystal solvent content: new insights via nonparametric kernel density
  estimate”, *Acta Crystallographica D*, 70 (2014), 1579–1588,
  [doi:10.1107/S1399004714005550](https://doi.org/10.1107/S1399004714005550).
- K. A. Kantardjieff and B. Rupp, “Matthews coefficient probabilities:
  Improved estimates for unit cell contents of proteins, DNA, and
  protein–nucleic acid complex crystals”, *Protein Science*, 12 (2003),
  1865–1871,
  [doi:10.1110/ps.0350503](https://doi.org/10.1110/ps.0350503).

## Dynamic copy range

The workflow has no configured scientific copy ceiling. For each exact or
bounded sequence mass it enumerates every positive integer copy count from one
through the final count whose sequence-mass interval can still leave
non-negative solvent volume: `floor(V_ASU / (1.23 * minimum_sequence_mass))`.
The backend is `asu_sequence_mass_physical_volume_v2`. Configured solvent limits
are analysis preferences and never clip that physical enumeration. Both low-
and high-solvent tails, including 9% and 91% under a 10%-90% window, are
reviewable. Each row publishes the configured limits and `within`, `overlaps`
or `outside` window status separately from physical status. Under the declared
positive-protein-volume model, intervals entirely below zero solvent or at/above
one are inconsistent; an interval partially intersecting the valid range keeps
its mass uncertainty. The zero-solvent limiting state is review-only, not a
claim of realistic packing. A count of
100,000 is only a fail-closed corruption/resource guard and must never truncate
a valid analysis.

The historical pre-RF audit enumerated 76,767 hypotheses and reached maxima
of 72, 171, and 19 copies for `AD4QS1P4G2_18`, `CD4QS2P2G1_15`, and
`CD6QS2P2G1_5`. The bounded funnel still emits exactly 25 candidates per
crystal. Those counts describe the superseded clipped window and are not
qualification of the physical-volume backend. No new unknown-crystal run is
required to validate this mathematical change.

Exceptional solvent contents outside conventional ranges are documented by
C. X. Weichenberger, P. V. Afonine, K. Kantardjieff and B. Rupp,
"The solvent component of macromolecular crystals", *Acta Crystallographica D*
71 (2015), 1023-1038, [doi:10.1107/S1399004715006045](https://doi.org/10.1107/S1399004715006045).

## Inputs, outputs, and failure semantics

Inputs are the exact crystal manifest, pipeline configuration, MTZ preflight
records, sequence groups, and source-protein records. Outputs are the complete
Matthews JSONL, TSV, Parquet and Markdown inventories. Each hypothesis binds the
preflight, sequence group, copy count, probability backend, and dynamic-range
backend and `mattprob_factor_evidence_v1` evidence contract in its content identity.
Each current row includes the relative solvent density, empirical copy frequency,
their product, observed copy-count occurrences, copy-reference population size,
resolution-selected density-reference count, density backend and reference SHA-256.
`positive`/`zero` density and `observed`/`unobserved` copy frequency remain separate
states. Historical records with no factor evidence retain null fields; partial
factor records, inconsistent products/frequencies and mismatched status labels
fail validation. Current production admission additionally rederives every
factor and reference binding, so absent historical fields cannot qualify a new
funnel. JSONL, TSV, Parquet and the review HTML/TSV expose these raw features.

Malformed reference bytes, a checksum mismatch, unsupported backend metadata,
insufficient resolution-conditioned observations, invalid mass/volume/solvent
bounds, or a dynamic range beyond the corruption guard fails the stage. A
physically impossible one-copy diagnostic remains reported but is not retained
for execution; it is a scientific state, not an
execution failure. An unobserved `P(n)` has a prior weight of zero but remains
eligible for explicit review and later evidence.

No external executable or network service is required at runtime. The
developer-only builder requires the exact checksum-pinned published ZIP archive
and writes deterministic gzip bytes.

## Verification

Focused tests cover reference checksums, record counts, resolution selection,
kernel values, empirical copy frequencies, dynamic ranges beyond 16, invalid
inputs, high-copy small-protein demotion without filtering, funnel identities,
dual Matthews/MR ranking, and installed-wheel resource parity. RF-G3 additionally
covers both window tails, complete finite ranges, out-of-window funnel admission,
and downstream copy-state eligibility. The 0.9 A insufficient-reference case
fails explicitly rather than using a coarser resolution or a zero score.
Factor reporting tests preserve exact and bounded products, distinguish empirical
zeros from missing evidence, round-trip all raw fields through the tabular outputs,
and reject altered factor evidence at the production funnel boundary.
RF-G2's explicit selection route and the known-control RF-G4 comparison complete
reachability and scientific qualification; historical unknown-crystal counts
cannot substitute for those gates.
