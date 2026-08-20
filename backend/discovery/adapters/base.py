from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol


@dataclass
class RawPosting:
    company: str
    role_title: str
    source: str
    source_url: str
    location: Optional[str] = None
    raw_description: Optional[str] = None
    posted_date: Optional[date] = None


class Adapter(Protocol):
    def fetch(self) -> list[RawPosting]:
        ...
