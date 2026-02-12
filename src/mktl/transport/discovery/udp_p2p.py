import socket
import threading
import time
from typing import List, Tuple

from .base import Discovery


CALL = b"I heard it"
RESPONSE_PREFIX = b"on the X:"


class P2PServer:
    def __init__(self, rep_port: int, listen_port: int):
        self.rep_port = int(rep_port)
        self.listen_port = listen_port

        self._sock = None
        self._running = False
        self._seen = {}
        self._delay = 1

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', self.listen_port))

        self._sock = sock
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except:
            pass

    def _loop(self):
        response = RESPONSE_PREFIX + str(self.rep_port).encode()

        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
            except:
                break

            now = time.time()
            last = self._seen.get(addr, 0)

            if last + self._delay > now:
                continue

            if data.strip() == CALL:
                self._sock.sendto(response, addr)
                self._seen[addr] = now


class P2PDiscovery(Discovery):
    def __init__(self, port):
        self.port = port
        self._found: List[Tuple[str, int]] = []

    def start(self):
        pass

    def stop(self):
        self._found.clear()

    def peers(self):
        return list(self._found)

    def search(self, wait=True):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1)

        sock.sendto(CALL, ('255.255.255.255', self.port))

        found = []
        start = time.time()

        while time.time() - start < 1:
            try:
                data, server = sock.recvfrom(4096)
            except:
                break

            if data.startswith(RESPONSE_PREFIX):
                rep = int(data[len(RESPONSE_PREFIX):])
                found.append((server[0], rep))

                if not wait:
                    break

        self._found = found
        return found
