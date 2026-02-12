"""Discovery / hello message type (transport-agnostic)."""

from abc import ABC, abstractmethod
from typing import Iterable, Dict, Any


class Discovery(ABC):

    # lifecycle
    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    # query known endpoints
    @abstractmethod
    def peers(self) -> Iterable[Dict[str, Any]]:
        pass

    # optional immediate advertise
    def announce(self):
        pass
