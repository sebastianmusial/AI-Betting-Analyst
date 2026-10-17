"""Walk-forward Dixon-Colesa: refit co blok czasu, trening WYŁĄCZNIE na meczach przed blokiem.

Bloki domyślnie tygodniowe od piątku do czwartku (`W-THU`): football-data zbiera kursy
przedmeczowe w piątek (weekend) i we wtorek (środek tygodnia), więc model dla bloku
nie widzi żadnego wyniku z dnia decyzji ani późniejszego.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from betting_analyst.models.dixon_coles import fit_dixon_coles

log = logging.getLogger(__name__)

DC_COLUMNS = ["dc_home", "dc_draw", "dc_away", "dc_over", "dc_under"]


def block_starts(dates: pd.Series, freq: str) -> pd.Series:
    """Początek bloku (okresu) dla każdej daty meczu."""
    return dates.dt.to_period(freq).dt.start_time


def walk_forward_dc(
    matches: pd.DataFrame,
    league: str,
    *,
    freq: str = "W-THU",
    window_days: int = 3 * 365,
    xi: float = 0.0018,
    min_matches: int = 100,
    predict_from: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Prognozy DC dla każdego meczu z `matches` (od `predict_from`), bez patrzenia w przyszłość.

    `matches`: kolumny match_id, date, home_team, away_team, home_goals, away_goals.
    Zwraca: match_id, dc_* (NaN, gdy drużyna nieznana lub za mało historii),
    `train_max_date` (ostatni mecz w treningu), `fit_date` (początek bloku).
    """
    data = matches.sort_values("date", kind="stable").reset_index(drop=True)
    data["block"] = block_starts(data["date"], freq)
    targets = data if predict_from is None else data[data["date"] >= predict_from]
    rows: list[dict] = []
    for start, block in targets.groupby("block", sort=True):
        train = data[(data["date"] < start) & (data["date"] >= start - timedelta(days=window_days))]
        model = None
        if len(train) >= min_matches:
            try:
                model = fit_dixon_coles(train, league, xi=xi, fitted_at=start.to_pydatetime())
            except Exception as exc:  # optymalizator potrafi nie zbiec — mecz bez prognozy
                log.warning("DC %s %s: dopasowanie nieudane: %s", league, start.date(), exc)
        train_max = train["date"].max() if len(train) else pd.NaT
        for match in block.itertuples(index=False):
            pred = model.predict(match.home_team, match.away_team) if model is not None else None
            row = {"match_id": match.match_id, "train_max_date": train_max, "fit_date": start}
            for col in DC_COLUMNS:
                row[col] = pred[col.removeprefix("dc_")] if pred else np.nan
            rows.append(row)
    return pd.DataFrame(rows, columns=["match_id", *DC_COLUMNS, "train_max_date", "fit_date"])
