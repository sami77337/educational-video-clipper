"""Domain models for video clipping."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClipRequest:
    """Represents a requested video clip range."""

    source: str
    start_seconds: int
    end_seconds: int
    output_name: str
