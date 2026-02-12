from . import message
from . import publish
from . import request


"""
mKTL Protocol Layer
===================

This package defines the transport-agnostic messaging protocol used by mKTL.
It provides semantic message structures, construction utilities, and a
user-facing facade that sits above transport/session implementations.

The protocol layer MUST NOT depend on any transport implementation
(e.g. ZeroMQ, RabbitMQ, etc).

---------------------------------------------------------------------

Layer Architecture Overview
---------------------------

User Code
    │
    ▼
Protocol Facade (protocol.py)
    High-level semantic API
    - get()
    - set()
    - publish()
    - request()
    Hides builder + session details

    │
    ▼
Message Builder (factory.py)
    Fluent construction of protocol messages
    - Ensures consistent envelope creation
    - Applies defaults / metadata
    - No transport awareness

    │
    ▼
Message Model (message.py)
    Immutable protocol data structures
    - Envelope
    - Message
    - MsgType
    Defines semantic meaning only

    │
    ▼
Field Vocabulary (fields.py)
    Canonical names for envelope/meta keys
    Prevents string drift across system

---------------------------------------------------------------------

Below the Protocol Layer (for context)
--------------------------------------

Session Layer
    Executes communication semantics
    - request()
    - publish()
    - subscribe()

Codec / Framing Layer
    Maps Message <-> wire frames

Transport Layer
    Moves bytes
    - ZeroMQ
    - RabbitMQ
    - etc.

---------------------------------------------------------------------

Design Principles
-----------------

1. Transport Agnostic
   Protocol must operate identically regardless of backend.

2. Semantic Purity
   Message meaning defined here, not by transport behavior.

3. Layer Isolation
   Dependencies only flow downward:
       Protocol -> Session -> Transport
   Never upward.

4. Ergonomic API
   Most users interact only with the Protocol facade.

---------------------------------------------------------------------
"""


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
