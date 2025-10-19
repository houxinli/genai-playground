"""Rating fetcher abstractions."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class RatingResult:
    """Represents a single rating returned by an external provider."""

    source: str
    score: float
    scale: float
    url: str
    summary: Optional[str] = None
    confidence: float = 0.5


class RatingFetcher(abc.ABC):
    """Base interface for third-party rating providers."""

    source: str

    def __init__(self, *, timeout: int = 15) -> None:
        self.timeout = timeout

    @abc.abstractmethod
    def fetch(self, title: str, *, year: Optional[int] = None) -> Optional[RatingResult]:
        """Return the best rating result for the given title."""

