mKTL is intended to be the successor to the Keck Task Library (KTL)
applications programming interface (API) at W. M. Keck Observatory (WMKO).
The goal of KTL is to standardize interprocess communications, providing a
common API to access commands and telemetry for systems across the observatory,
regardless of the specific communication method (mKTL, EPICS, MUSIC, RPC, etc.)
used by that system.

As the successor to KTL, mKTL is intended to be a super-set of the fundamental
publish/subscribe and request/response aspects of KTL; the main departures for
mKTL, as compared to KTL, focus on usability.

 * Where KTL requires the local installation of several major pieces
   of kroot, mKTL is intended to install as a standalone package with
   minimal dependencies.

 * Where KTL requires the client to have local support for a specific
   communication method, mKTL will use a universal protocol based on
   `JSON <https://www.json.org>`_ and `ZeroMQ <https://zeromq.org/>`_
   for every client/daemon interaction.

 * Where KTL requires the installation of local configuration data for a
   client to access a service, mKTL will discover any/all service metadata
   at run time.

In addition to usability mKTL also places a strong emphasis on performance,
with sufficiently lightweight handling to allow high frequency (greater
than a kilohertz) and high bandwidth (greater than 10 gigabit/sec)
applications.

The documentation for mKTL is published here:

https://keckobservatory.github.io/mKTL/
