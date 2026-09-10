# PDB sequence references without coordinate mappings

The PDB sequence database retains a bare entry identifier with an absent SEQRES
suffix, such as `36za_`, as sequence evidence. An absent suffix is not a known
blank author-chain ID. Do not invent a chain or entity, discard the sequence,
or treat a matching catalogue candidate as ineligible.

The `target_mapping.tsv` columns remain unchanged. A complete suffix uses
`legacy_seqres_suffix`; an absent bare-entry suffix uses
`unavailable_seqres_suffix` with the original empty token. The normalised FASTA
retains the original target ID and sequence. Entry IDs are case-insensitive;
non-empty suffixes remain case-sensitive. Invalid entry IDs, whitespace,
malformed assembly identifiers, duplicate records and invalid sequences still
fail. Readers reject inconsistent target, entry, namespace or token fields.

MMseqs2 still searches the retained sequence and reports its unmodified alignment
metrics. A matching result remains `completed_hit` / `hits_found`, not `no_hit`.
The structural reference is `deferred`, its `target_chain_or_entity` is null,
and its raw metrics explicitly record `coordinate_mapping_status=unavailable`
and `missing_seqres_suffix`. The per-query warning and aggregate unavailable-hit
count distinguish sequence evidence from coordinate availability.

Coordinate registration does not fetch or register a deferred reference. The M6
model policy retains its rejected-model annotation with reason
`coordinate_mapping_unavailable`; it cannot become an MR-model input. Catalogue
sequences and all their original record mappings remain in the candidate
universe. Existing model budgets and scientific thresholds are unchanged.

Newly prepared sequence resources record the unavailable-reference count and
the `retain_missing_seqres_suffix_as_sequence_only_v1` mapping policy. Mapping
files are checksum-inventoried. The PDB sequence adapter is
`pdb-sequence-mmseqs-v5` and the M6 model-policy adapter is
`m6-trusted-model-policy-v4`, so old cached interpretation is not reused.

Validation covers record conservation, unavailable-versus-blank distinction,
malformed and contradictory mappings, retained search scores and hit status,
coordinate-registration exclusion, M6 model-admission exclusion and unchanged
candidate retention. Real database qualification still requires the separate
functional smoke and anchored full-checksum verification; local parser tests
alone do not establish native qualification.
