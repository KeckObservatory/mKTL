mKTL is intended to be the successor to the Keck Task Library (KTL)
applications programming interface (API) at W. M. Keck Observatory (WMKO).
The goal of KTL is to standardize interprocess communications, providing a
common API to access commands and telemetry for systems across the observatory,
regardless of the specific communication method (EPICS, MUSIC, RPC, etc.) used
by that system.

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

Despite the emphasis on usability there is a strong desire to improve the
latency and throughput of commands; early testing suggests that these
improvements are within reach. Additional features, such as bulk data
transmission and 'structured' key/value pairs, are also being considered
as key improvements over the original capabilities of KTL.
