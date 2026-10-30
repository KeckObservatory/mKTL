.. _heritage:

Heritage
========

History
-------

The development of the Keck Task Library (KTL) has its origins in the early 1990’s,  motivated by the need for a common API to standardize access to commands and telemetry from disparate systems across `W. M. Keck Observatory <https://keckobservatory.org/>`_ (WMKO). The first light instruments at WMKO were HIRES, LRIS, and NIRC; HIRES and LRIS had some measure of common heritage and relied on MUSIC messaging, developed by `University of California Observatories <https://www.ucobservatories.org/>`_ at the `UC Santa Cruz <https://www.ucsc.edu/>`_ campus, for interprocess communications; NIRC used a system based on the `remote procedure call <https://en.wikipedia.org/wiki/Sun_RPC>`_ (RPC) library from `Sun Microsystems <https://en.wikipedia.org/wiki/Sun_Microsystems>`_; the telescope control system uses the `Experimental Physics and Industrial Control System <https://epics-controls.org/>`_ (EPICS). The KTL API is a set of C routines, implemented as a shared library, that provides a common key/value behavior layered on top of these disparate communication APIs.

The entry point for any KTL client is to load a shared library unique to the KTL service of interest, where a KTL service is a collection of individual KTL keywords, and where a keyword is a single key/value pair. This KTL client library can be any C code, so long as it implements the methods that the KTL API expects to find. The earliest instruments took full advantage of this opportunity, with custom code implementing the interface to each of their respective communication methods; later instruments relied on common, configuration-driven libraries that were shared across instruments; each of the three communication styles (EPICS, MUSIC, and RPC) has an implementation intended to be shared across many services and/or instruments, though there isn’t much common heritage between the three, and certain optional aspects of the KTL API are poorly supported, or not supported at all, in some of the variants; as a result, shared KTL tools are required to be aware of implementation-specific variances in order to function correctly, and some specific applications cannot be shared because they rely on implementation-specific behavior.

With that background in mind, let it be stated clearly that KTL was unambiguously successful in its broader objectives. New instruments progressively leaned further on KTL as a key technology, with more services, more dispatchers, more keywords, and overall, more KTL-driven information flow though each system. The telescope control system and adaptive optics benches at WMKO did not realize the same level of benefit, as the development for those systems focused on using EPICS directly as a first-class interface, enabled KTL-based access to a limited subset of commands and telemetry, and often do not use the KTL abstraction for internal tools. KTL also saw widespread adoption at Lick Observatory, where it is used as a first-class interface for all commands and telemetry; University of California Observatories' oversight of LicK Observatory and the UC participation in WMKO encouraged this practice, and it yielded substantial improvements to both KTL and common KTL tools across both observatories.

In order for mKTL to succeed it must be better than KTL. While this assertion is simple to write down there will be both qualitative and quantitative metrics that must be met in order to achieve that broader objective. Three decades of KTL development, maintenance, and support provide a wealth of experience to draw from; care must be taken to emphasize the successful design choices made with KTL, while minimizing or eliminating the areas where it was less successful. mKTL is not positioned as a rejection of KTL: mKTL is an evolution, drawing from an established heritage, and avoiding the missteps of the past must not come at the expense of making new missteps that KTL successfully evaded.


Strengths
---------

The strengths identified here highlight areas to emphasize when making design decisions for mKTL.

Key/value pairs
^^^^^^^^^^^^^^^

Representing commands and telemetry as key/value pairs has been an excellent match for the usage patterns at WMKO. Sensor values, motor positions, filter names, etc., all lend themselves to having a single value, or family of values, representing vital state information for a given system. Being able to address keywords individually is an important part of this approach, as it allows client applications to work with exactly the subset of commands and telemetry they need, instead of requiring manipulation of a bulkier, more complex structure.

Request/response
^^^^^^^^^^^^^^^^

A request/response pattern is fundamental to both synchronous and asynchronous usage in KTL. The KTL command exchange involves two steps: a first stage notification, acknowledging that a request has been made, and a second stage notification, a full response indicating the completion of the request. The base pattern for this request/response exchange underpins the different handling options available to a KTL client: ignoring any response, continuing with execution before checking for a response, and blocking execution until a response is received. Each of these patterns is essential for different types of client interactions.

Publish/subscribe
^^^^^^^^^^^^^^^^^

A publish/subscribe pattern allows for asynchronous handling of new values; this is particularly valuable for event-driven use cases, where recording, displaying, or otherwise reacting to a new value should occur immediately rather than wait for a client polling cycle to occur. Publish/subscribe also unlocks additional efficiency, in that a single publish event can be distributed to all subscribers in a single pass, rather than requiring subscribers to individually poll for new values via the request/response interface.

Flexible values
^^^^^^^^^^^^^^^

Every KTL keyword value has two representations: ‘ascii’ and ‘binary’, which have different meanings depending on the defined keyword type. This behavior, while optional, has powerful practical use: a boolean keyword, for example, may have 0 and 1 as its available binary values, but the ascii values could be anything: off and on, no and yes, false and true, or whatever other values might be handled by that service’s KTL client library. This behavior extends to enumerated and mask keyword types, where a binary integer value can be interpreted as arbitrary strings. This allows the possibility that a client can work directly with human-readable values for command and telemetry instead of relying on the correct handling of magic numbers to achieve the same goal. This same basic feature is used to render numeric values in multiple different units, such as the binary value being in radians and the ascii value in degrees, or as sexagesimal.

Distributed control
^^^^^^^^^^^^^^^^^^^

There is no single source of authority for KTL; there is no federated naming scheme, or any requirement that what is installed on one computer matches what is installed on another. Any naming scheme must only be unique locally, and does not register itself with a persistent registry running elsewhere in order to function correctly. In practice, most KTL services have unique names, and uniqueness is generally a virtue, though for specific use cases, such as testing, there is merit in being able to run any KTL service in an isolated environment. Any KTL client, as long as it satisfies its prerequisites, can communicate with any KTL dispatcher, without invoking an intermediary; any one KTL dispatcher (or family of dispatchers) does not have common infrastructure that might be bottlenecked by some other dispatcher (or dispatchers). In practice, this allows instruments to operate independently of each other, limiting the likelihood that a failure affecting one system might degrade performance for another.

Multiple languages
^^^^^^^^^^^^^^^^^^

One of the virtues of a C-based API is that every other language has a mechanism to access that API; some languages have several. Regardless, the ubiquitous ability to access C code from other languages has been of enduring value to expand KTL access beyond its original intended use. Language-specific KTL interfaces for Tcl, Java, and Python all see production use.


Weaknesses
----------

The weaknesses identified here highlight areas to avoid when making design decisions for mKTL.

C-based API
^^^^^^^^^^^

While a C-based API has merit it has also proven to be a weakness for KTL. The KTL API relies on an ioctl interface for much of its optional functionality; the arguments to the defined ioctl commands vary in both number and type, and switching ioctl behavior is governed by a single 32-bit integer, which limits the number of optional commands that might be added to the API. Any expansion of the API beyond its current footprint creates binary incompatibility, where interoperability between systems becomes critically impaired and could motivate a mass rebuild across any interconnected systems.  And, just because access to a C-based API is possible from a given language doesn’t mean it’s easy; for example, KTL relies on a union type (a KTL polymorph) to contain telemetry values, which must be handled with care when the value is exposed to a strongly typed language, like Java.

Interface layer
^^^^^^^^^^^^^^^

With KTL being primarily a C-based API, the key interface layer between a client application and the dispatcher receiving the command is this C API. A client’s application code is custom up until that point; on the other side of the interface, the code associated with the persistent daemon takes over, including all aspects of on-the-wire communication between the KTL client library and the dispatcher. This design decision means that client interactions cannot be cleanly isolated from dispatcher handling, because the behavior of the dispatcher-specific messaging requires code specific to that messaging on the client side.

Code complexity
^^^^^^^^^^^^^^^

The implementation of the KTL API is a complex collection of C code, having grown organically from the base concepts of the API to include logging behavior, backgrounded queueing and dispatching of events, and additional hooks for optional behavior added to the API over time. Support exists for different types of messaging, of which only one style of messaging is ever used. Making changes in any one area often has unintended consequences elsewhere in the code base; eliminating memory leaks is one example, where memory allocation occurs in one file, but deallocation must occur elsewhere, or in a different context entirely; some allocations occur in the client library but are freed by the KTL API, and the reverse also occurs. So, this code complexity extends to the KTL client libraries themselves, and the amount of close coupling across that API layer is high.

Multiple communcation styles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One of the key design goals of KTL was to implement a common abstraction to manage differences in communication style between different systems, each potentially employing a unique protocol and transport for inter-process communication. While it was successful in this regard, it also created circumstances leading to some of its largest flaws: any communication failures require deep protocol-specific knowledge in order to diagnose and remedy the failure; any client wishing to communicate with a given system must locally install all libraries appropriate for the communication method(s) used by that system; each KTL client library is an isolated code base, and is on its own to successfully map KTL calls to its native method of communication, with significant variance in how successful they actually are. The net result is that it is not sufficient to be an expert in an application-specific protocol and transport, it is not sufficient to be an expert in the KTL API, proper maintenance requires an individual to be expert in both areas in order to succeed.

Prerequisite knowledge
^^^^^^^^^^^^^^^^^^^^^^

Having the correct KTL client library installed locally is generally insufficient to access the KTL service; some amount of additional information must be provided, such as environment variables defining a target host name, or configuration files describing how the client library should connect to the waiting KTL dispatcher. These configuration management quirks are a barrier to usage, and depending on their nature, delicate and prone to configuration mismatches.

.. _dependencies:

Exotic dependencies
^^^^^^^^^^^^^^^^^^^

The use of KTL is tied to a WMKO standard deployment of kroot; this includes the KTL API shared libraries, the KTL client libraries for the specific KTL services of interest, configuration files used by those KTL client libraries, and command line utilities providing common functionality for scripts as well as interactive use. Any KTL-based software must therefore have a full kroot install available in order to function normally; this is perhaps not a burden for systems that must have kroot regardless, but the close coupling between KTL and kroot is an easy example of an exotic dependency. Individual client libraries create their own burdens in this respect: an EPICS-based client library must have enough EPICS available locally to build and run; likewise for MUSIC, which is bundled in kroot, and RPC, which despite being an industry standard, WMKO’s KTL RPC implementation relies on GNU libc extensions that were deprecated and removed, and multithreaded behavior that was present in Solaris but not ported to Linux. Some dependencies are less exotic, but can still cause problems at build and run time, such as libxml2.

Performance
^^^^^^^^^^^

Typical KTL requests must pass through several handling steps on their way to their destination, and the same is true for any response. The handoff between the C API and any KTL client library implementation establishes multiple places where queueing and threading are natural structures to control the flow of data; these queues, signaling steps, and translations result in lost time, either to increased latency, or a need for processing power, or both. This effect is not egregious, in that the original use cases likely did not intend for KTL to achieve frequencies higher than 100 Hz; performance up to an appreciable fraction of a kilohertz has been attained, though not relied on. Nevertheless, KTL is actively avoided for high frequency or low latency communications.

Bundling keywords
^^^^^^^^^^^^^^^^^

The KTL API treats keywords as isolated entities; there is no provision for linking multiple keywords into an atomic unit, either for commands or telemetry. Consider the case where a telescope is commanded to move: the right ascension and declination must both be specified as separate keywords, and then a third keyword triggered in order to begin the move. Consider the case of a motorized mechanism, which may have multiple encoders, motor power feedback, and other telemetry; KTL does not provide a method for a client to confidently assert that a set of telemetry is a self consistent snapshot of a system’s state.

Bulk data
^^^^^^^^^

The KTL API provides limited support for numeric arrays, which are effectively associative arrays; while this does in part address the bundling concern noted directly above, that is only true if the keywords are all numeric, and either all integers or all floating point numbers. Support for these array types is limited, both in terms of array size and in which KTL client libraries allow their use. The transport of an image buffer is one example of the type of data that falls outside what the KTL API can support.


Decision criteria
-----------------

The strengths and weaknesses described above can be distilled to a handful of guiding principles, listed in order of decreasing significance.

Ubiquity
^^^^^^^^

It is inevitable that mKTL will need to be implemented in multiple languages, not just Python, in order to maintain acceptance as an observatory standard over a multi-decade time span. Any approaches embedded in mKTL, and any key external technologies leveraged by mKTL, must therefore be ubiquitous and readily available across not just languages of choice, but generally available as standard options for a broad range of languages. This increases the odds that future languages are likely to provide similar support. Widespread adoption also implies widespread familiarity with the technologies and approaches, which could give new developers a head start on their introduction to mKTL.

Portability
^^^^^^^^^^^

The concept of portability may be derivative of ubiquity; regardless, mKTL and its dependencies must be readily buildable on a diverse set of potential platforms and architectures. This increases the odds that future platforms and architectures are likely to provide similar support.

Simplicity
^^^^^^^^^^

mKTL and its dependencies must not impose undue complexity in order to leverage their key functionality. Simple dependencies will allow mKTL code to remain clean and easy to follow, rather than impose their own structure on the design or implementation; mKTL itself should likewise seek to minimize boilerplate requiredfor its use.

Features
^^^^^^^^

mKTL and its dependencies must provide compelling features. For dependencies, if the cost of reimplementing specific functionality is low it is likely preferable to avoid the additional dependency entirely; for mKTL, the feature set should remain targeted to its core functionality, largely in support of achieving the other goals outlined here.

Performance
^^^^^^^^^^^

mKTL and its dependencies must be adequately performant such that the overall performance is not degraded by their use.


Core dependencies
-----------------

With these principles as guideposts, mKTL has adopted two key external technologies as foundational components for its functional goals: `ZeroMQ <https://zeromq.org/>`_ as a network transport, and `JSON <https://www.json.org/>`_ as a data interchange format.

Support for ZeroMQ spans virtually every programming language in use today, well beyond the set of languages of potential interest to the mKTL community; because of its widespread use and extensive history it is also the type of technology that will have a long tail of maintenance as it ages, even if it is no longer being actively developed. The features of ZeroMQ are also well aligned with the goals of mKTL, with respect to enabling a distributed architecture, having low overhead and high performance, transparent reconnect logic, and usage patterns that mimic simple sockets. By a happy coincidence ZeroMQ also implements an efficient PUB/SUB pattern well-suited to mKTL's functional requirements.

Similarly, JSON enjoys ubiquitous support for all modern programming languages, surpassed possibly only by XML; XML's gains in language support are offset by its bulky structure and inefficiency of parsing. JSON parsing is likewise inefficient and represents a significant source of processing overhead for mKTL messages; this inefficiency is accepted as it is not onerous enough to cause mKTL to miss its performance goals. Being able to natively represent numeric, string, boolean, and sequence data in JSON relieves mKTL of the need to invent its own parsing or complex message payload scheme; being able to represent the description of a store's items in JSON also eliminates ambiguity about the proper formatting of mKTL metadata.


Requirements
------------

The mKTL project did not start with a formal requirements phase; the
requirements captured here are derived from different phases of the mKTL
prototyping, starting with initial concepts, and following with a combination
of emergent requirements and implementation guidelines.

Each of the requirements listed here includes a short description of the
intent of the requirement, along with how it ties into the heritage described
in this document.


Pre-development
^^^^^^^^^^^^^^^

  #. **The fundamental data model of mKTL shall be a key/value store.**

     The key/value design pattern has been tremendously successful for KTL,
     and shows no sign of decreasing in relevance for our environment. Leaning
     into that strength has to be at the core of mKTL.

  #. **mKTL shall implement a request/response pattern.**

     A request/response pattern is a fundamental component of all interactive
     behavior in an event-driven system; this is the means by which a client
     requests change in a system, and receives guaranteed updates for a value.

  #. **mKTL shall enable both blocking and non-blocking request/response
     patterns.**

     One of KTL's unique strengths for its request/response pattern is the
     concept of a first-stage notification, effectively an acknowledgement
     that a request has been received, followed later by a second-stage
     response indicating that a request is complete. A client is not required
     to block until a request is complete, but they have the option to; this
     flexibility directly enables different types of interactive behavior
     without the need for additional special handling of the commands.

  #. **mKTL synchronous request/response performance shall be capable of
     1,000 operations per second for a single item.**

     The vast majority of use cases for mKTL do not require command throughput
     at the kilohertz level; most requests are intermittent, ocurring far less
     frequently than 1 hertz. This requirement has two goals: one, overall
     efficiency, in that supporting high performance cases should help
     minimize the cost of processing a lesser stream of requests, and two,
     enabling the use of mKTL in environments where we might otherwise rely
     on a custom method for interprocess communications, or some other
     less-familiar means of request handling.

  #. **mKTL shall implement a publish/subscribe pattern.**

     A publish/subscribe pattern enables asynchronous, event-driven behavior;
     a basic implementation of this pattern, combined with the key/value
     representation of commands and telemetry, enables persistent downstream
     applications, such as graphical user interfaces and higher-level logic
     layered on top of other mKTL interfaces. The pattern implemented here
     must allow subscriptions at the individual item level; a client should
     not receive messages for items it is not using.

  #. **mKTL publishing rates shall be capable of 10,000 operations per second
     for a single item.**

     The logic for this requirement is similar to the performance requirement
     for request/response operations, but because publish operations occur
     far more often than request/response interactions there is a stronger
     need for both efficiency and throughput.

  #. **mKTL shall provide a means to automatically discover daemons on the
     local network.**

     Properly bootstrapping a KTL environment to have access to a given KTL
     service is a barrier to use; in order to reduce both startup costs and
     the risk of configuration error mKTL will provide some form of discovery
     mechanism that enables a new client, with no other metadata, to identify
     authoritative sources of information and proceed with normal
     request/response and publish/subscribe operations.

  #. **mKTL clients shall not be limited to contacting a single mKTL daemon.**

     Some KTL-based systems fell into a trap where connection support was
     restricted to a single KTL service for any one application; mKTL shall
     not be limited in this fashion. mKTL clients, which includes mKTL daemons,
     shall be able to connect to any number of mKTL daemons, limited only by
     system resources. mKTL is intended for use with highly distributed
     systems, with each authoritative component working in isolation from
     any others, with the explicit goal of enabling clients and other
     applications that wish to communicate with as many or as few authoritative
     sources of information as needed for that specific application.

  #. **mKTL shall use a single transport for all request/response and
     publish/subscribe messaging.**

     This directly addresses the weakness of KTL related to multiple
     communication styles; the use of a single transport, and clearly
     defining the transport and protocol, allows the on-the-wire
     messaging to be the entire boundary between different mKTL
     implementations, without the need to carry around prerequisites
     or any awareness of nuances that may occur between implementations.

  #. **mKTL shall use a single message format for request/response interactions,
     and a single message format for publish/subscribe interactions.**

     Similar to the above, this is part of the promise mKTL is making to
     future users of the system: there will be no gap or incompatibility
     as a result of a change to the on-the-wire message format.

  #. **mKTL shall use JSON as its payload encoding scheme.**

     There are other, more optimal encoding schemes, but none have the universal
     support offered by JSON, combined with a reasonable degree of human
     readability. The use of JSON allows native encoding of every value type
     presently in use with KTL: integers, floating point numbers, strings,
     booleans, and so on. It also provides native support for sequences, and
     for the absence of data (a null value).

  #. **mKTL shall allow the transmission of arbitrary binary data.**

     This directly addresses the weakness of KTL related to the
     transmission of bulk data. By providing an option to transmit arbitrary
     binary data mKTL will be capable of transmitting binary blobs such as
     image buffers; one could imagine a set of mKTL items representing an
     entire FITS file, with the headers and image HDU(s) transmitted as
     different items, and the possible future combination of these items
     into a single aggregate item for atomic handling.


Development
^^^^^^^^^^^

This next set of requirements came about during the initial prototyping and
development. These requirements represent an extended standard, beyond the
pre-development requirements, that supported mKTL implementations adhere to.

  #. **mKTL shall adhere to commonly understood terms and nomenclature whenever
     possible.**

     The use of KTL-specific language is a barrier to adoption. Where
     well-understood terms are already in common use they should apply
     directly to the same concepts in mKTL; for example, the use of key/value
     pairs, and those terms being used consistently throughout mKTL when
     referring to their respective concepts.

  #. **mKTL shall be maintained as an independent open source project without
     explicit dependencies on other WMKO infrastructure.**

     The use of a WMKO-specific build environment is a barrier to adoption,
     as are any WMKO-specific dependencies. mKTL should be fully functional
     in an environment with no other WMKO-specific heritage or expertise.
     mKTL shall be installable as a standalone package, but it is also
     expected to be installable via traditional WMKO software deployment
     practices.

  #. **mKTL shall be maintained indefinitely by WMKO.**

     WMKO is making a commitment as a long-term user and maintainer of mKTL.
     Other institutions are welcome to use mKTL and contribute to its ongoing
     maintenance, though no warranty is expressed or implied: WMKO does not
     have the resources to provide end-user support outside its core mission.
     The commitment here is that mKTL will not be abandoned by WMKO, and there
     will always be a core group of maintainers for the project.

  #. **mKTL shall be served to the community through a WMKO-managed source code
     repository.**

     This is perhaps a corollary of the indefinite maintenance, but the source
     code for mKTL shall always be in a location that is managed by WMKO,
     whether it is locally or externally hosted.

  #. **The initial mKTL implementation shall be written in Python.**

     Python is the language most relevant to the pool of potential mKTL
     developers. This will change with time, so while Python is the language
     of choice today, future mKTL development may focus on a different
     language, so any Python-specific details need to be irrelevant for
     the core aspects of mKTL message handling.

  #. **mKTL implementations shall avoid the use of non-standard packages.**

     Exotic dependencies introduce unwanted fragility with respect to
     long-term support. See the section on :ref:`exotic
     dependencies<dependencies>` for a more complete motivation.

  #. **mKTL shall provide a rapid (0.1 second or better) error in the event
     that the daemon handling a request is not responding.**

     It should not be necessary to wait for an extended timeout to occur
     before a client can confidently assert that no entity is available to
     handle a request. The two-stage notification process described above,
     and the absence of the first-stage acknowledgement, is a systematic
     way to quickly assert that no proper response is forthcoming.

  #. **mKTL subscriptions shall connect automatically when a client
     instantiates an item.**

     Common usage of object-oriented KTL interfaces follows a pattern where
     an object is instantiated and then immediately subscribes to future
     broadcast events. By default, mKTL should eliminate this boilerplate,
     and always subscribe to future broadcasts, but do so in a way that
     does not block execution of the application.

  #. **mKTL subscriptions shall reconnect automatically.**

     In no circumstances should a client be required to implement logic to
     reconnect to an authoritative daemon in order to continue receiving
     updates; all reconnect logic, if not handled entirely in the transport
     layer, must be completely transparent to both the client and daemon.

  #. **mKTL clients shall not exit automatically if a subscription fails.**

     Likewise, when a subscription occurs but the receiving daemon is not
     online, this should never be a fatal error; the client should reconnect
     automatically once the daemon is online and normal operations resume.

  #. **mKTL shall provide a capability for clients to register callbacks
     on a per-item basis.**

     Callback methods represent a common usage pattern for event-driven
     systems, where the callback method is invoked every time the locally
     known value updates. Efficient handling of callbacks, including the
     option of registering transient callbacks that get garbage collected,
     is a key enabler for different event-driven approaches. It is a practical
     necessity that callbacks be executed in the background, so that events
     arriving via a network buffer can be efficiently queued without waiting
     for a potentially expensive callback method to complete execution.

  #. **mKTL shall provide a command line tool to perform simple operations.**

     The command-line tools offered for KTL are not just debugging tools,
     they are commonly used for inspection of systems and for basic shell
     scripting. mKTL must provide a similar command line interface, minimally
     supporting get and set operations, as well as monitoring a broadcast
     stream of published events. Where mKTL supports different representations
     for an item's value the command-line tool must provide similar support.
     Because this tool will be used for scripting it must likewise be efficient,
     and not represent a major source of overhead for the application at large.

