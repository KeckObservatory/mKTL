# POT

POT (final naming and nomenclature to-be-determined) is intended to be the
successor to the Keck Task Library (KTL) applications programming interface
(API) at W. M. Keck Observatory (WMKO). The goal of KTL is to standardize
interprocess communications, providing a common API to access commands and
telemetry for systems across the observatory, regardless of the specific
communication method (EPICS, MUSIC, RPC, etc.) used by that system.

As the successor to KTL, POT is intended to be a super-set of the fundamental
publish/subscribe and request/response aspects of KTL; the main departures for
POT, as compared to KTL, focus on usability.

 * Where KTL requires the local installation of several major pieces
   of kroot, POT is intended to install as a standalone package with
   minimal dependencies.

 * Where KTL requires the client to have local support for a specific
   communication method, POT clients will use a single communication method
   for all services.

 * Where KTL requires the installation of local configuration data for a
   client to access a service, POT will discover any/all service metadata
   at run time.
