""" A simple broadcast UDP discovery method. A persistent server would fire up a
    :class:`Server` instance, and clients would use the func:`search` method
    to find any available listeners.

    No other information is exchanged beyond establishing that a
    :class:`Server` is running on a specific address. Clients can then attempt
    more interesting questions once they know which addresses might participate
    in answering those questions.
"""

import os
import socket
import threading
import time

from .. import config

call = 'I heard it'
call = call.encode()

response = 'on the X:'
response = response.encode()

# There's nothing special about this port number, other than it is not
# privileged, and happens to be prime. It is effectively a shared secret.

default_port = 10103

# The default port is used for discovery of intermediaries, registries that are
# willing to cache and share second-hand information aggregated from one or
# more authoritative daemons, and be the first stop for any new clients on
# the network. The direct port is used by last-stop daemons, those that are
# authoritative for their respective stores; the registries will use this direct
# port to discover them.

direct_port = 10111


class Server:
    """ Listen for any queries on the default port; respond to any queries
        with our current IP address and the *rep* port we were provided.
        This allows clients to discover a valid location where they can issue
        real requests.
    """

    port = default_port

    def __init__(self, rep):
        self.delay = 1
        self.seen = dict()
        self.socket = None
        self.thread = None

        rep = int(rep)
        rep = str(rep)
        rep = rep.encode()
        self.response = response + rep

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(('', self.port))
        except OSError:
            return

        self.socket = sock
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def cleanup(self):
        try:
            self.socket.close()
        except:
            pass

        self.socket = None
        self.seen = dict()
        self.thread = None


    def run(self):

        while True:
            try:
                data, address = self.socket.recvfrom(4096)
            except:
                break

            now = time.time()

            try:
                last_response = self.seen[address]
            except KeyError:
                last_response = 0

            if last_response + self.delay > now:
                # Throttling responses to this client, we already corresponded
                # with them in recent memory.
                continue

            data = data.strip()
            if data == call and self.socket is not None:
                self.socket.sendto(self.response, address)
                self.seen[address] = now


        self.cleanup()


# end of class Server



class DirectServer(Server):
    """ Same as the :class:`Server`, but intended for use by authoritative
        daemons answering only for themselves, not aggregating content from
        any other sources.
    """

    port = direct_port

    def __init__(self, rep):
        return Server.__init__(self, rep)


# end of class DirectServer



def search(port=default_port, wait=False, targets=tuple()):
    """ Find locally available :class:`Server` instances. If *wait* is True, the
        search will delay returning until multiple instances have an opportunity
        to respond; otherwise, the fastest responding instance will be included
        in the returned list and there will be no additional delay.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1)

    targets = list(targets)

    if port == default_port:
        cached = preload_registries()
        targets.extend(cached)

    for target in targets:
        targeted_address = (target, port)
        sock.sendto(call, targeted_address)

    broadcast_address = ('255.255.255.255', port)
    sock.sendto(call, broadcast_address)

    start = time.time()
    expiration = 1
    elapsed = 0

    found = list()

    try:
        timeouts = (TimeoutError, socket.timeout)
    except AttributeError:
        # socket.timeout was deprecated in 3.10, in favor of TimeoutError.
        timeouts = (TimeoutError,)

    while elapsed < expiration:
        try:
            data, server = sock.recvfrom(4096)
        except timeouts:
            now = time.time()
            elapsed = now - start
            continue
        except BlockingIOError:
            # We came back through the loop after setting the socket to be
            # non-blocking, having found at least one server response. Time
            # to return results.
            break
        else:
            now = time.time()
            elapsed = now - start

        data = data.strip()
        if response in data:
            rep = data[len(response):]
            rep = int(rep)
            found.append((server[0], rep))

            if wait == True:
                sock.settimeout(expiration - elapsed)
            else:
                # Set the timeout to zero so that the next attempt to read from
                # the socket will exit with a non-blocking error if there is no
                # further data to be read. We could just return here, but if
                # multiple clients responded simultaneously, we'd like to give
                # them the chance to be in the returned list of available
                # servers-- but if not, we don't want to wait around for further
                # responses, let the searcher move on to asking real questions.
                sock.settimeout(0)
        else:
            sock.settimeout(expiration - elapsed)

    if port == default_port:
        remember_registries(found)

    return found


def search_direct(port=direct_port, wait=True):
    """ The same as :func:`search`, but looking for :class:`DirectServer`
        instances listening on the alternate port.
    """

    return search(port, wait)


def preload_registries():
    """ Helper method to parse environment variables and cached files on
        disk to build a list of addresses to check for registry availability.
    """

    directory = config.directory()
    client = os.path.join(directory, 'client')
    manual = os.path.join(client, 'registries')
    cached = os.path.join(client, 'registries.cache')

    lines = list()

    try:
        contents = open(manual, 'r').read()
    except FileNotFoundError:
        pass
    else:
        lines.extend(contents.split('\n'))

    try:
        contents = open(cached, 'r').read()
    except FileNotFoundError:
        pass
    else:
        lines.extend(contents.split('\n'))


    registries = ''

    for line in lines:
        line = line.split('#')[0]
        registries = registries + ' ' + line

    registries = registries.strip()

    if registries == '' or registries is None:
        registries = tuple()
    else:
        registries = registries.split()

    return registries


def remember_registries(found):
    """ Cache any found registries for future requests. There is no provision
        for removing registries that no longer respond, this may become
        necessary in the future-- if the cached set grows unbounded there may
        become a point where the occasional UDP broadcast becomes a burden
        rather than a minor inefficiency.
    """

    directory = config.directory()
    client = os.path.join(directory, 'client')
    cached = os.path.join(client, 'registries.cache')

    if os.path.exists(client):
        pass
    else:
        os.makedirs(client, mode=0o775)


    lines = set()

    try:
        contents = open(cached, 'r').read()
    except FileNotFoundError:
        contents = tuple()
    else:
        contents = contents.split('\n')

    for line in contents:
        line = line.split('#')[0]
        line = line.strip()

        if line != '':
            lines.add(line)

    for address,rep in found:
        lines.add(address)

    lines = list(lines)
    lines.sort()
    lines.insert(0, '# This file is generated automatically.')
    contents = '\n'.join(lines)


    writer = open(cached, 'w')
    writer.write(contents + '\n')
    writer.close()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
