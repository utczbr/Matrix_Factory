from physical_engine.optimization.numba_ops import calculate_compression_work

class CompressorStage:
    """Tier 1: ideal-gas polytropic work (numba_ops.calculate_compression_work,
    already implements exactly the W = (gamma/(gamma-1))*(mR T1/eta)*[(P2/P1)^x - 1]
    formula doc2 §4.2 would otherwise have you re-derive)."""
    def __init__(self, eta_isentropic: float = 0.75):
        self.eta = eta_isentropic

    def power_kw(self, mdot_kg_s: float, t_in_k: float, p_in_bar: float, p_out_bar: float) -> float:
        if mdot_kg_s <= 0 or p_in_bar <= 0:
            return 0.0
        work_j = calculate_compression_work(
            p1=p_in_bar * 1e5, p2=p_out_bar * 1e5, mass=mdot_kg_s,
            temperature=t_in_k, efficiency=self.eta,
        )
        return work_j / 1000.0  # J/s -> kW (mass is already a rate here)
