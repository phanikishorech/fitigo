from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


VisitorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class BookingVisitorsRequest(BaseModel):
    visitor_names: list[VisitorName] = Field(min_length=1, max_length=50)