"""Per-env HCL emitters. _CODEGEN maps env name -> emitter."""

from .finance import _emit_finance_codegen
from .identity import _emit_identity_codegen
from .perimeter import _emit_perimeter_tag_codegen
from .observability import _emit_observability_codegen
from .network import _emit_network_codegen, _emit_vpn_codegen
from .secgroups import _emit_sgacl_codegen

_CODEGEN = {
    "02-finance":      _emit_finance_codegen,
    "03-identity":     _emit_identity_codegen,
    "04-perimeter":    _emit_perimeter_tag_codegen,
    "06-observability": _emit_observability_codegen,
    "05-network":      _emit_network_codegen,
    "10-network-vpn":  _emit_vpn_codegen,
    "11-network-sgacl": _emit_sgacl_codegen,
}
