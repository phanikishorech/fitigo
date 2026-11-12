from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

TicketCategory = Literal['ACCOUNT', 'BOOKING', 'GYM', 'TECHNICAL', 'OTHER']
TicketStatus = Literal['OPEN', 'WAITING_USER', 'RESOLVED']


class SupportInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    body: str = Field(min_length=1, max_length=2000)

    @field_validator('body', mode='before')
    @classmethod
    def clean_body(cls, value):
        if isinstance(value, str):
            if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                raise ValueError('Control characters are unsupported')
            return value.strip()
        return value


class SupportCreate(SupportInput):
    category: TicketCategory
    subject: str = Field(min_length=1, max_length=120)

    @field_validator('subject', mode='before')
    @classmethod
    def clean_subject(cls, value):
        if isinstance(value, str):
            if any(ord(c) < 32 for c in value): raise ValueError('Subject must be a single line')
            return value.strip()
        return value


class SupportReply(SupportInput):
    expected_version: int = Field(ge=1)


class SupportStatusChange(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    status: TicketStatus
    expected_version: int = Field(ge=1)