from datetime import date

from fastapi import HTTPException


def reporting_range(date_from: date | None, date_to: date | None, *, day: date | None = None) -> tuple[date, date] | None:
    """Validate inclusive report dates; preserve legacy single-date/no-filter calls."""
    if date_from is None and date_to is None:
        if day is None:
            return None
        date_from, date_to = day, day
    elif day is not None:
        raise HTTPException(status_code=422, detail="Use either date or date_from/date_to, not both")
    if date_from is None or date_to is None:
        raise HTTPException(status_code=422, detail="Both date_from and date_to are required")
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="Start date must not be after end date")
    if (date_to - date_from).days >= 366:
        raise HTTPException(status_code=422, detail="Select a date range of at most 366 days")
    # The exclusive timestamp boundary needs a representable following day.
    if date_from == date.min or date_to == date.max:
        raise HTTPException(status_code=422, detail="Dates are outside the supported reporting range")
    return date_from, date_to