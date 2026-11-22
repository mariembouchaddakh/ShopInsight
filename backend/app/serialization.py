"""Conversion des sorties d'agents en JSON strict (numpy, pandas, NaN → null), sans modifier leur contenu."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(o, pd.Timestamp):
        return None if pd.isna(o) else o.isoformat()
    if o is pd.NaT:
        return None
    return o


def evidence_snapshot(log) -> list[dict]:
    """Copie du journal de preuves d'un agent (attribut public `log`) : identifiant, nature, source, contenu."""
    return [jsonable({"id": e.id, "kind": e.kind, "source": e.source, "payload": e.payload}) for e in log.with_prefix("")]
