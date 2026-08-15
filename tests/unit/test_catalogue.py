"""Tests for trusted catalogue import, identity, mass, and annotation adapters."""

import json
from pathlib import Path

import polars as pl
import pytest
import yaml
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from genome_to_diffraction.catalogue import (
    CatalogueImportRequest,
    CatalogueImportResult,
    import_catalogues,
)
from genome_to_diffraction.catalogue.annotations import read_gbff, read_gff
from genome_to_diffraction.catalogue.mass import assess_mass
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]


def _write_config(path: Path, *, policy: str = "warn", min_length: int = 1) -> None:
    document = yaml.safe_load(
        (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8")
    )
    document["catalogue"]["ambiguous_residue_policy"] = policy
    document["catalogue"]["min_length_aa"] = min_length
    path.write_text(json.dumps(document), encoding="utf-8")


def _write_manifest(
    path: Path,
    fasta: Path,
    *,
    locus_map: Path | None = None,
    annotation_gff: Path | None = None,
    annotation_gbff: Path | None = None,
) -> None:
    entry: dict[str, object] = {
        "catalogue_id": "trusted_a",
        "proteome_faa": str(fasta),
        "annotation_provider": "synthetic trusted provider",
        "annotation_version": "test-1",
        "is_contaminant_catalogue": False,
    }
    if locus_map is not None:
        entry["protein_locus_map"] = str(locus_map)
    if annotation_gff is not None:
        entry["annotation_gff"] = str(annotation_gff)
    if annotation_gbff is not None:
        entry["annotation_gbff"] = str(annotation_gbff)
    path.write_text(
        json.dumps({"schema_version": "1.0", "catalogues": [entry]}),
        encoding="utf-8",
    )


def _run_import(
    tmp_path: Path,
    fasta_text: str,
    *,
    policy: str = "warn",
    min_length: int = 1,
    locus_text: str | None = None,
) -> CatalogueImportResult:
    inputs = tmp_path / "inputs with spaces"
    inputs.mkdir(parents=True)
    fasta = inputs / "trusted proteins.faa"
    fasta.write_text(fasta_text, encoding="utf-8")
    locus = None
    if locus_text is not None:
        locus = inputs / "protein loci.tsv"
        locus.write_text(locus_text, encoding="utf-8")
    manifest = tmp_path / "catalogues.json"
    config = tmp_path / "config.json"
    _write_manifest(manifest, fasta, locus_map=locus)
    _write_config(config, policy=policy, min_length=min_length)
    return import_catalogues(
        CatalogueImportRequest(manifest, config, tmp_path / "output with spaces", False)
    )


def test_import_groups_exact_sequences_and_preserves_duplicate_ids(
    tmp_path: Path,
) -> None:
    result = _run_import(
        tmp_path,
        ">protein_1 first copy\nac de*\n"
        ">protein_2 same exact sequence\nACDE\n"
        ">protein_1 distinct duplicate identifier\nACDF\n",
        locus_text=(
            "protein_id\tlocus_tag\tcontig\tstart\tend\tstrand\tgene_name\tproduct\n"
            "protein_1\tLOC1\tcontig_1\t10\t21\t+\tgeneA\tprotein A\n"
            "protein_2\tLOC2\tcontig_1\t30\t41\t-\tgeneB\tprotein B\n"
        ),
    )
    assert len(result.source_records) == 3
    assert len(result.sequence_groups) == 2
    grouped = {group.sequence: group for group in result.sequence_groups}
    assert grouped["ACDE"].source_record_count == 2
    assert grouped["ACDE"].molecular_mass_da == pytest.approx(436.4375)
    assert "terminal_stop_removed" in grouped["ACDE"].quality_flags
    duplicate_sources = [
        source
        for source in result.source_records
        if source.original_protein_id == "protein_1"
    ]
    assert len({source.source_record_id for source in duplicate_sources}) == 2
    assert all(
        "duplicate_original_protein_id" in source.quality_flags
        for source in duplicate_sources
    )
    assert all(source.locus_tag == "LOC1" for source in duplicate_sources)


def test_ambiguous_mass_uses_bounds_and_internal_stop_has_no_mass(
    tmp_path: Path,
) -> None:
    result = _run_import(
        tmp_path,
        ">ambiguous\nABZJXUO\n>internal_stop\nAC*DE\n",
    )
    groups = {group.sequence: group for group in result.sequence_groups}
    ambiguous = groups["ABZJXUO"]
    assert ambiguous.molecular_mass_da is None
    assert ambiguous.molecular_mass_lower_da is not None
    assert ambiguous.molecular_mass_upper_da is not None
    assert ambiguous.molecular_mass_lower_da < ambiguous.molecular_mass_upper_da
    assert "ambiguous_residue_X" in ambiguous.quality_flags
    assert "defined_nonstandard_residue_U" in ambiguous.quality_flags
    stopped = groups["AC*DE"]
    assert stopped.molecular_mass_da is None
    assert stopped.molecular_mass_lower_da is None
    assert "internal_stop" in stopped.quality_flags
    fasta = (tmp_path / "output with spaces/exact_sequences.faa").read_text(
        encoding="utf-8"
    )
    assert ambiguous.sequence_group_id in fasta
    assert stopped.sequence_group_id not in fasta


def test_defined_nonstandard_residues_have_exact_review_mass() -> None:
    assessment = assess_mass("AUO")
    assert assessment.exact_da is not None
    assert assessment.lower_da is None
    assert assessment.residue_policy == "defined_nonstandard_exact_review"


def test_ambiguity_policy_error_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ambiguous_residue_policy=error"):
        _run_import(tmp_path, ">ambiguous\nAXA\n", policy="error")


def test_ambiguity_policy_exclude_removes_sequence_from_search_fasta(
    tmp_path: Path,
) -> None:
    result = _run_import(tmp_path, ">ambiguous\nAXA\n", policy="exclude")
    assert "excluded_ambiguous_or_nonstandard_residue" in (
        result.sequence_groups[0].quality_flags
    )
    assert not (tmp_path / "output with spaces/exact_sequences.faa").read_text(
        encoding="utf-8"
    )


def test_outputs_are_deterministic_valid_and_include_parquet(tmp_path: Path) -> None:
    first = _run_import(tmp_path / "first", ">protein_1\nACDEFG\n")
    second = _run_import(tmp_path / "second", ">protein_1\nACDEFG\n")
    assert first.manifest.import_id == second.manifest.import_id
    assert first.sequence_groups[0].sequence_group_id == (
        second.sequence_groups[0].sequence_group_id
    )
    first_output = tmp_path / "first/output with spaces"
    assert pl.read_parquet(first_output / "sequence_groups.parquet").height == 1
    assert pl.read_parquet(first_output / "source_records.parquet").height == 1
    manifest = json.loads(
        (first_output / "catalogue_import_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["sequence_group_count"] == 1
    assert len(manifest["outputs"]) == 8
    assert (
        load_contract(
            first_output / "catalogue_import_manifest.json",
            "catalogue-import-manifest",
            progress=False,
        ).model_dump(mode="json")["import_id"]
        == first.manifest.import_id
    )
    group_lines = (first_output / "sequence_groups.jsonl").read_text(encoding="utf-8")
    source_lines = (first_output / "source_records.jsonl").read_text(encoding="utf-8")
    SequenceGroupRecord.model_validate_json(group_lines)
    SourceProteinRecord.model_validate_json(source_lines)


def test_gff_and_gbff_adapters_preserve_locus_coordinates(tmp_path: Path) -> None:
    gff = tmp_path / "annotation.gff"
    gff.write_text(
        "##gff-version 3\n"
        "contig_1\tprovider\tCDS\t5\t34\t.\t-\t0\t"
        "ID=cds-protein_1;protein_id=protein_1;locus_tag=LOC1;"
        "gene=abc;product=ATP%20protein\n",
        encoding="utf-8",
    )
    gff_record = read_gff(gff)["protein_1"][0]
    assert (gff_record.start, gff_record.end, gff_record.strand) == (5, 34, "-")
    assert gff_record.product == "ATP protein"

    gbff = tmp_path / "annotation.gbff"
    record = SeqRecord(Seq("ATG" * 20), id="contig_2", name="contig_2")
    record.annotations["molecule_type"] = "DNA"
    record.features.append(
        SeqFeature(
            FeatureLocation(3, 33, strand=1),
            type="CDS",
            qualifiers={
                "protein_id": ["protein_2"],
                "locus_tag": ["LOC2"],
                "gene": ["def"],
                "product": ["binding protein"],
            },
        )
    )
    SeqIO.write(record, gbff, "genbank")
    gbff_record = read_gbff(gbff)["protein_2"][0]
    assert (gbff_record.start, gbff_record.end, gbff_record.strand) == (4, 33, "+")
    assert gbff_record.locus_tag == "LOC2"


def test_gff_adapter_merges_compatible_compound_cds_segments(tmp_path: Path) -> None:
    gff = tmp_path / "compound.gff"
    common = (
        "ID=cds-WP_1.1;Parent=gene-LOC1;Name=WP_1.1;"
        "exception=ribosomal%20slippage;locus_tag=LOC1;"
        "product=IS630%20family%20transposase;protein_id=WP_1.1"
    )
    gff.write_text(
        "##gff-version 3\n"
        f"contig_1\tPGAP\tCDS\t509\t976\t.\t-\t0\t{common}\n"
        f"contig_1\tPGAP\tCDS\t56\t507\t.\t-\t0\t{common}\n",
        encoding="utf-8",
    )

    metadata = read_gff(gff)["WP_1.1"][0]

    assert (metadata.start, metadata.end, metadata.strand) == (56, 976, "-")
    assert metadata.locus_tag == "LOC1"
    assert metadata.product == "IS630 family transposase"
    assert metadata.gene_name is None
    assert "compound_cds_segments_merged" in metadata.quality_flags


def test_gff_adapter_rejects_conflicting_compound_cds_segments(
    tmp_path: Path,
) -> None:
    gff = tmp_path / "conflicting-compound.gff"
    gff.write_text(
        "##gff-version 3\n"
        "contig_1\tPGAP\tCDS\t509\t976\t.\t-\t0\t"
        "protein_id=WP_1.1;locus_tag=LOC1;product=transposase\n"
        "contig_2\tPGAP\tCDS\t56\t507\t.\t-\t0\t"
        "protein_id=WP_1.1;locus_tag=LOC1;product=transposase\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting contig for split CDS"):
        read_gff(gff)


def test_catalogue_import_preserves_multiple_loci_for_one_protein(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "proteins.faa"
    fasta.write_text(">WP_1.1 shared protein\nACDEFGHIK\n", encoding="utf-8")
    gff = tmp_path / "annotation.gff"
    gff.write_text(
        "##gff-version 3\n"
        "contig_1\tPGAP\tCDS\t10\t36\t.\t+\t0\t"
        "ID=cds-1;protein_id=WP_1.1;locus_tag=LOC1;product=protein\n"
        "contig_2\tPGAP\tCDS\t50\t76\t.\t-\t0\t"
        "ID=cds-2;protein_id=WP_1.1;locus_tag=LOC2;product=protein\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "catalogues.json"
    config = tmp_path / "config.json"
    _write_manifest(manifest, fasta, annotation_gff=gff)
    _write_config(config)

    result = import_catalogues(
        CatalogueImportRequest(manifest, config, tmp_path / "output", False)
    )

    assert len(result.source_records) == 2
    assert len(result.sequence_groups) == 1
    assert result.sequence_groups[0].source_record_count == 2
    assert {record.locus_tag for record in result.source_records} == {"LOC1", "LOC2"}
    assert all(
        "multiple_compatible_loci" in record.quality_flags
        for record in result.source_records
    )


def test_progress_and_structured_logs_are_visible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fasta = inputs / "proteins.faa"
    fasta.write_text(">protein_1\nACDEFG\n", encoding="utf-8")
    manifest = tmp_path / "catalogues.json"
    config = tmp_path / "config.json"
    _write_manifest(manifest, fasta)
    _write_config(config)
    from genome_to_diffraction.cli import main

    assert (
        main(
            [
                "--log-format",
                "json",
                "catalogue",
                "import",
                "--catalogues",
                str(manifest),
                "--config",
                str(config),
                "--outdir",
                str(tmp_path / "output"),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "Import catalogues" in captured.err
    assert '"message": "catalogue import complete"' in captured.err
