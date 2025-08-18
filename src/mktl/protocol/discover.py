""" A simple broadcast UDP discovery method. A persistent server would fire up a
    :class:`Server` instance, and clients would use the func:`search` method
    to find any available listeners.

    No other information is exchanged beyond establishing that a
    :class:`Server` is running on a specific address. Clients can then attempt
    more interesting questions once they know which addresses might participate
    in answering those questions.
"""

import socket
import threading
import time

call = 'I heard it'
call = call.encode()

response = 'on the X:'
response = response.encode()

# There's nothing special about this port number, other than it is not
# privileged, and happens to be prime. It is effectively a shared secret.

default_port = 10103

# The default port is used for discovery of intermediaries, daemons that are
# willing to cache and share second-hand information aggregated from one or
# more authoritative daemons, and be the first stop for any new clients on
# the network. The direct port is used by last-stop daemons, those that are
# authoritative for their respective stores; the intermediaries will use this
# direct port to find them.

direct_port = 10111


class Server:
    """ Listen for any queries on the default port; respond to any queries
        with our current IP address and the *request* port we were provided.
        This allows clients to discover a valid location where they can issue
        real requests.
    """

    port = default_port

    def __init__(self, request):
        self.delay = 1
        self.seen = dict()
        self.socket = None
        self.thread = None

        request = int(request)
        request = str(request)
        request = request.encode()
        self.response = response + request

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

    def __init__(self, request):
        return Server.__init__(self, request)


# end of class DirectServer



def search(port=default_port, wait=False):
    """ Find locally available :class:`Server` instances. If *wait* is True, the
        search will delay returning until multiple instances have an opportunity
        to respond; otherwise, the fastest responding instance will be included
        in the returned list and there will be no additional delay.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1)

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
        # Presumably at some point socket.timeout will go away.
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
            request = data[len(response):]
            request = int(request)
            found.append((server[0], request))

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

    return found


def search_direct(port=direct_port, wait=True):
    """ The same as :func:`search`, but looking for :class:`DirectServer`
        instances listening on the alternate port.
    """

    return search(port, wait)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
