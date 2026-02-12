from typing import List, Tuple
from .base import Discovery


class BrokerDiscovery(Discovery):
    """
    Discovery through configured broker endpoints.
    """

    def __init__(self, brokers: List[Tuple[str, int]]):
        self._brokers = brokers

    def start(self):
        pass

    def stop(self):
        pass

    def peers(self):
        return list(self._brokers)

    def search(self):
        return list(self._brokers)
