"""Small public synthetic inputs for the internal identification profile."""

import gzip
import hashlib
from pathlib import Path

import gemmi
import numpy as np

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.identification_inputs import (
    SPEC_RELATIVE,
    CrystalInput,
    IdentificationCase,
    IdentificationPlan,
    copy_priors,
    expected_case_id,
)
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
)


def materialise_identification_fixture(
    repository: Path, *, group_count: int = 3, all_ready: bool = False
) -> tuple[Path, IdentificationPlan]:
    root = repository / "identification-inputs"
    (root / "coordinates").mkdir(parents=True)
    mtz = gemmi.Mtz(with_base=True)
    mtz.spacegroup = gemmi.find_spacegroup_by_name("P 1")
    mtz.set_cell_for_all(gemmi.UnitCell(30, 31, 32, 90, 90, 90))
    mtz.add_dataset("synthetic")
    mtz.add_column("I", "J")
    mtz.add_column("SIGI", "Q")
    mtz.add_column("FreeR_flag", "I")
    mtz.set_data(
        np.array([[1, 1, 1, 100, 10, 0], [2, 1, 1, 50, 5, 1]], dtype=np.float32)
    )
    mtz_path = repository / "synthetic.mtz"
    mtz.update_reso()
    mtz.write_to_file(str(mtz_path))
    crystal = CrystalInput(
        crystal_id="synthetic_crystal",
        mtz=str(mtz_path),
        mtz_sha256=sha256_file(mtz_path),
        observation_labels="I,SIGI",
        free_r_test_value=0,
        space_group="P 1",
        asu_volume_a3=mtz.cell.volume,
        resolution_high_a=mtz.resolution_high(),
        reflection_count=2,
        symmetry_multiplicity=1,
        minimum_mass_da=300.0,
        maximum_mass_da=600.0,
    )
    lines = [
        f"ATOM  {i:5d}  CA  {name} B{i:4d}    "
        f"{float(i):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           C"
        for i, name in enumerate(("ALA", "CYS", "ASP", "GLU"), start=1)
    ]
    structure = gemmi.read_pdb_string("\n".join([*lines, "END", ""]))
    structure.name = "1ABC"
    structure.setup_entities()
    structure.entities[0].full_sequence = ["ALA", "CYS", "ASP", "GLU"]
    coordinate = root / "coordinates/1ABC.cif.gz"
    coordinate_text = (
        structure.make_mmcif_document()
        .as_string()
        .replace(
            "_entity_poly.pdbx_seq_one_letter_code\n",
            "_entity_poly.pdbx_seq_one_letter_code_can\n",
        )
    )
    coordinate.write_bytes(gzip.compress(coordinate_text.encode("ascii"), mtime=0))
    groups = []
    sources = []
    cases = []
    for index in range(group_count):
        sequence = "ACDQ" + "A" * index
        digest = hashlib.sha256(sequence.encode()).hexdigest()
        group = SequenceGroupRecord(
            schema_version="1.0",
            sequence_group_id=f"seq_{digest}",
            sha256=digest,
            sequence=sequence,
            length_aa=len(sequence),
            molecular_mass_da=400.0,
            mass_method="synthetic fixture mass",
            residue_policy="standard_exact",
            source_record_count=1,
        )
        groups.append(group)
        source = SourceProteinRecord(
            schema_version="1.0",
            source_record_id=f"source_{index}",
            catalogue_id="synthetic_catalogue",
            original_protein_id=f"protein_{index}",
            original_header=f"protein_{index}",
            sequence_group_id=group.sequence_group_id,
            source_annotation_provider="synthetic",
        )
        sources.append(source)
        hit = StructuralSearchHit(
            schema_version="1.0",
            hit_id=f"hit_{index}",
            sequence_group_id=group.sequence_group_id,
            provider="pdb_sequence_mmseqs",
            provider_rank=1,
            target_id="1abc_B",
            model_key="pdb:1ABC:legacy_seqres_suffix:B",
            target_chain_or_entity="B",
            pdb_id="1ABC",
            identifier_namespace="legacy_seqres_suffix",
            query_start=1,
            query_end=4,
            target_start=1,
            target_end=4,
            aligned_length=4,
            query_coverage=1.0,
            target_coverage=1.0,
            sequence_identity=0.75,
            evalue=1e-20,
            bits=100.0,
            database_id="synthetic_database",
            raw_result_pointer="raw/results.tsv",
            raw_metrics={
                "target_sequence_length": 4,
                "target_sequence_sha256": hashlib.sha256(b"ACDE").hexdigest(),
            },
            eligibility_status="selected",
            eligibility_reason="synthetic eligible hit",
        )
        copies, priors = copy_priors(crystal, 400.0)
        ready = all_ready or index == 0
        cases.append(
            IdentificationCase(
                case_id=expected_case_id(crystal, group.sequence_group_id),
                crystal_id=crystal.crystal_id,
                sequence_group_id=group.sequence_group_id,
                accessions=(source.original_protein_id,),
                product="synthetic protein",
                mass_da=400.0,
                status="ready" if ready else "model_unavailable",
                reason="synthetic fixture disposition",
                hit=hit if ready else None,
                coordinate_file="coordinates/1ABC.cif.gz" if ready else None,
                coordinate_sha256=sha256_file(coordinate) if ready else None,
                component_copies=copies,
                copy_priors=priors,
            )
        )
    (root / "sequence_groups.jsonl").write_text(
        "".join(g.model_dump_json() + "\n" for g in groups)
    )
    (root / "source_records.jsonl").write_text(
        "".join(s.model_dump_json() + "\n" for s in sources)
    )
    plan = IdentificationPlan(
        discovery_package_id="synthetic_discovery",
        sequence_groups_sha256=sha256_file(root / "sequence_groups.jsonl"),
        source_records_sha256=sha256_file(root / "source_records.jsonl"),
        crystals=(crystal,),
        cases=tuple(cases),
    )
    atomic_write_json(root / "plan.json", plan.model_dump(mode="json"))
    spec = repository / SPEC_RELATIVE
    spec.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(spec, {"schema_version": "1.0", "input_root": str(root)})
    spec.chmod(0o600)
    return root, plan
