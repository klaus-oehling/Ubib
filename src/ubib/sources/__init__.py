"""Source adapters and the source registry.

Each adapter subclasses :class:`ubib.sources.base.Source` and declares a unique
``id`` matching the ``source`` column in the catalog. ``get_source`` returns a
ready-to-use instance.
"""

from __future__ import annotations

from .abs import ABS
from .anac import ANAC
from .anp import ANP
from .banxico import Banxico
from .base import Source
from .bcch import BCCh
from .bea import BEA
from .bloomberg import Bloomberg
from .bls import BLS
from .caged import CAGED
from .cielo import Cielo
from .comexstat import ComexStat
from .ecb import ECB
from .eurostat import Eurostat
from .fred import FRED
from .imf import IMF
from .ine_spain import INESpain
from .inegi import INEGI
from .ipea import IPEA
from .olinda import Olinda
from .ons import ONS
from .sgs import SGS
from .sidra import SIDRA
from .statcan import StatCan
from .tesouro_direto import TesouroDireto
from .tesouro_rmd import TesouroRMD
from .tesouro_rtn import TesouroRTN
from .us_census import USCensus
from .worldbank import WorldBank

_SOURCE_CLASSES: tuple[type[Source], ...] = (
    ABS, ANAC, ANP, Banxico, BCCh, BEA, Bloomberg, BLS, CAGED, Cielo, ComexStat,
    ECB, Eurostat, FRED, IMF, INESpain, INEGI, IPEA, Olinda, ONS, SGS, SIDRA,
    StatCan, TesouroDireto, TesouroRMD, TesouroRTN, USCensus, WorldBank,
)

#: Mapping of source id -> adapter instance.
REGISTRY: dict[str, Source] = {cls.id: cls() for cls in _SOURCE_CLASSES}


def get_source(source_id: str) -> Source:
    """Return the adapter instance for ``source_id`` (raises ``KeyError``)."""
    key = source_id.lower()
    try:
        return REGISTRY[key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown source '{source_id}'. Known sources: {sorted(REGISTRY)}"
        ) from exc


def available_sources() -> list[str]:
    """Sorted list of all registered source ids."""
    return sorted(REGISTRY)
