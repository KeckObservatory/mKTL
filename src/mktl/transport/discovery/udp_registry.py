import os
from typing import List

from .. import config
from .udp_p2p import CALL, RESPONSE_PREFIX, P2PDiscovery


class RegistryDiscovery(P2PDiscovery):

    def _preload(self) -> List[str]:
        directory = config.directory()
        manual = os.path.join(directory, 'client', 'brokers')
        cached = manual + '.cache'

        lines = []

        for path in (manual, cached):
            try:
                lines.extend(open(path).read().split('\n'))
            except FileNotFoundError:
                pass

        brokers = []
        for line in lines:
            line = line.split('#')[0].strip()
            if line:
                brokers.append(line)

        return brokers

    def _remember(self, found):
        directory = config.directory()
        client = os.path.join(directory, 'client')
        cached = os.path.join(client, 'brokers.cache')

        os.makedirs(client, exist_ok=True)

        lines = set()

        try:
            lines.update(open(cached).read().split('\n'))
        except FileNotFoundError:
            pass

        for addr, _ in found:
            lines.add(addr)

        cleaned = sorted(x.strip() for x in lines if x.strip())

        with open(cached, 'w') as f:
            f.write("\n".join(cleaned) + "\n")

    def search(self, wait=False):
        targets = self._preload()

        found = super().search(wait)

        if found:
            self._remember(found)

        return found
