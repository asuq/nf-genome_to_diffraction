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
protein identity. The unweighted solvent density remains available in the
runtime API and the MR review publishes an independent MR rank so disagreement
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
through the final count whose sequence-mass interval can still overlap the
configured minimum solvent fraction. Low-copy, high-solvent states are retained
and typed `review` or `impossible`; they are not silently omitted. A count of
100,000 is only a fail-closed corruption/resource guard and must never truncate
a valid analysis.

The current frozen-input audit enumerates 76,767 hypotheses and reaches maxima
of 72, 171, and 19 copies for `AD4QS1P4G2_18`, `CD4QS2P2G1_15`, and
`CD6QS2P2G1_5`. The bounded funnel still emits exactly 25 candidates per
crystal. High-copy small proteins remain visible, but the empirical `P(n)`
weight moves them behind better-supported ASU multiplicities instead of
silently deleting them.

## Inputs, outputs, and failure semantics

Inputs are the exact crystal manifest, pipeline configuration, MTZ preflight
records, sequence groups, and source-protein records. Outputs are the complete
Matthews JSONL, TSV, Parquet and Markdown inventories. Each hypothesis binds the
preflight, sequence group, copy count, probability backend, and dynamic-range
backend in its content identity.

Malformed reference bytes, a checksum mismatch, unsupported backend metadata,
insufficient resolution-conditioned observations, invalid mass/volume/solvent
bounds, or a dynamic range beyond the corruption guard fails the stage. A
physically impossible hypothesis is a retained scientific state, not an
execution failure. An unobserved `P(n)` has a prior weight of zero but remains
eligible for explicit review and later evidence.

No external executable or network service is required at runtime. The
developer-only builder requires the exact checksum-pinned published ZIP archive
and writes deterministic gzip bytes.

## Verification

Focused tests cover reference checksums, record counts, resolution selection,
kernel values, empirical copy frequencies, dynamic ranges beyond 16, invalid
inputs, high-copy small-protein demotion without filtering, funnel identities,
dual Matthews/MR ranking, and installed-wheel resource parity. The frozen-input
local audit must retain a 25/25/25 inventory before exact-source CI and a fresh
fixed-HPC screen can qualify the revised candidate selection.
