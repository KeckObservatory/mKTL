"""Transport interface.

This is the (small) contract that transport implementations should follow.
It lives outside :mod:`mktl.protocol` so the protocol remains transport-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..protocol import Message


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
    @abstractmethod
    def send(self, msg: Message) -> None:
        """Send a protocol message."""

    @abstractmethod
    def recv(self) -> Message:
        """Receive the next protocol message."""
