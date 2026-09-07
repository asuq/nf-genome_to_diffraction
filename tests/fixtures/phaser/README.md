# Selected Phaser evidence fixtures

`phenix_2_1_3u7q_selected.pdb` contains the first five native remarks from the
public 3U7Q parent control in immutable run
`gtd-heteromer-smoke-20260823T165137Z-68d216fad6dc-714eb859`.
Phenix 2.1-6048 used Phaser 2.8.4. The source PDB SHA-256 is
`e8794d52a865e1c9c318d23d0a61027395eb36e4711053d90aebdbbbaa72f6a1`;
it was rechecked against the normalised result bound by the retained
qualification checksum manifest. The original log SHA-256 is
`2e1d9620ff62381733b875a5594d8ce915e5d9429d1134cca27061883d07e5c2`.
The excerpt is parser evidence, not a complete coordinate model. Original
control records and v0.2 qualification history remain unchanged.

The precise final LLG is in the dedicated remark; the last TFZ and PAK in
the history remark belong to the selected final output. Earlier values
refer to preceding placement/refinement stages. Tests mutate this frozen
excerpt to exercise contradictions without relabelling synthetic variants
as native scientific evidence.

The positive `+TNCS` test cases use the annotation convention already retained
by the supported Phaser log parser. They test explicit interpretation and do
not claim a fresh native positive-tNCS qualification. A requested/observed
copy mismatch alone must never supply that annotation. See the official
[Phaser tNCS description](https://www.phaser.cimr.cam.ac.uk/index.php/Molecular_Replacement)
for the distinction between coupled searches and independently placed copies.
