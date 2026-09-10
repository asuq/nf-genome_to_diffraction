"""Preserve PDB sequence identifiers without inventing coordinate mappings.

The fixed SEQRES grammar admits a bare entry with an absent suffix as sequence
evidence only. Its explicit unavailable namespace differs from a known chain,
including a hypothetical blank author chain. Malformed entries and assembly
identifiers still fail. No network or external tools are used; the emitted
namespace/token are covered by database inventories and search-adapter cache
identities. Producer, table-reader and model-admission tests cover this boundary.
"""

import re
from dataclasses import dataclass
from typing import Literal

PdbSequenceNamespace = Literal["legacy_seqres_suffix", "unavailable_seqres_suffix"]
_TARGET = re.compile(
    r"^(?P<pdb_id>[0-9][A-Za-z0-9]{3})"
    r"(?:-assembly(?P<assembly_number>[1-9][0-9]*))?"
    r"_(?P<token>[^\s\t]*)$"
)


@dataclass(frozen=True, slots=True)
class PdbSequenceIdentifier:
    """A retained source identifier and its explicit coordinate-mapping state."""

    pdb_id: str
    namespace: PdbSequenceNamespace
    token: str

    @property
    def coordinate_mapping_available(self) -> bool:
        return self.namespace == "legacy_seqres_suffix"


def parse_pdb_sequence_identifier(target: str) -> PdbSequenceIdentifier:
    """Parse a complete token, or an explicitly unavailable bare-entry suffix."""

    match = _TARGET.fullmatch(target)
    if match is None or (
        not match.group("token") and match.group("assembly_number") is not None
    ):
        raise ValueError(f"unsupported PDB SEQRES target identifier: {target!r}")
    token = match.group("token")
    return PdbSequenceIdentifier(
        pdb_id=match.group("pdb_id").upper(),
        namespace="legacy_seqres_suffix" if token else "unavailable_seqres_suffix",
        token=token,
    )
