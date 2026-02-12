"""Transport interface.

This is the (small) contract that transport implementations should follow.
It lives outside :mod:`mktl.protocol` so the protocol remains transport-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..protocol.message import Message


# Transport agnostic exceptions

class TransportError(Exception):
    """Base class for all transport-layer errors."""


class TransportTimeout(TransportError):
    """A request did not receive a timely response."""


class TransportConnectionError(TransportError):
    """The transport could not establish or maintain a connection."""


class TransportPortError(TransportError):
    """No suitable port could be bound or connected."""


class Transport(ABC):
    """Minimal contract for a wire-level transport."""

    @abstractmethod
    def open(self) -> None:
        """Establish the underlying connection/socket."""

    @abstractmethod
    def close(self) -> None:
        """Tear down the underlying connection/socket."""

    @abstractmethod
    def send(self, msg: Message) -> None:
        """Send a protocol Message."""

    @abstractmethod
    def recv(self, timeout: Optional[float] = None) -> Message:
        """Receive the next protocol Message."""

    @property
    def is_open(self) -> bool:
        """Whether the transport is currently connected."""
        return False
