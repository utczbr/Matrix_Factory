"""
Station 1-4 stochastic parameter reference constants.

Defines the processing time distributions and defect rates for the
four mechanical assembly stations.  These constants serve as validation
references for the Phase 1 physical engine — actual stochastic sampling
occurs on the JVM side (Phase 2) using per-station, per-run-seeded
``java.util.SplittableRandom`` instances.

Reference: doc2 §2
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class StationParameters:
    """Immutable stochastic parameters for a manufacturing station.

    Attributes:
        name: Human-readable station name.
        t_mean_s: Mean processing time (seconds).
        t_std_s: Standard deviation of processing time (seconds).
        defect_rate: Probability of defect per unit [0, 1].
    """

    name: str
    t_mean_s: float
    t_std_s: float
    defect_rate: float


# Station parameter definitions per doc2 §2
STATION_PARAMS: Dict[int, StationParameters] = {
    1: StationParameters(
        name="MEA Preparation",
        t_mean_s=5.0,
        t_std_s=5.0,
        defect_rate=0.005,
    ),
    2: StationParameters(
        name="Catalytic Deposition",
        t_mean_s=12.0,
        t_std_s=15.0,
        defect_rate=0.012,
    ),
    3: StationParameters(
        name="Bipolar Plate Stamping",
        t_mean_s=3.0,
        t_std_s=2.0,
        defect_rate=0.002,
    ),
    4: StationParameters(
        name="Robotic Stack Assembly",
        t_mean_s=24.0,
        t_std_s=30.0,
        defect_rate=0.008,
    ),
}


def get_station_params(station_id: int) -> StationParameters:
    """Retrieve parameters for a specific station.

    Args:
        station_id: Station number (1-4).

    Returns:
        StationParameters for the requested station.

    Raises:
        KeyError: If *station_id* is not in {1, 2, 3, 4}.
    """
    if station_id not in STATION_PARAMS:
        raise KeyError(
            f"Unknown station ID {station_id}. "
            f"Valid IDs: {list(STATION_PARAMS.keys())}"
        )
    return STATION_PARAMS[station_id]
