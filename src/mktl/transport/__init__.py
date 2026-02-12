"""Transport layer implementations."""

import os

from .base import (
    TransportError,
    TransportTimeout,
    TransportConnectionError,
    TransportPortError,
)

_BACKEND = os.environ.get("MKTL_TRANSPORT", "zmq")

if _BACKEND == "zmq":
    from .zmq import request
    from .zmq import publish
# elif _BACKEND == "rabbitmq":
#     from .rabbitmq import request
#     from .rabbitmq import publish
else:
    raise ImportError(f"unknown MKTL_TRANSPORT backend: {_BACKEND!r}")
