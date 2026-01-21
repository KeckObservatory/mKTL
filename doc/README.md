The sphinx documentation for mKTL is generated automatically upon any changes
to the main branch. The generated documentation is published here:

https://keckobservatory.github.io/mKTL

This documentation set uses the Read the Docs theme; in addition to the
base sphinx packages, if being built on a Debian-derived Linux distribution
one might need to install the python3-sphinx-rtd-theme package (or similar),
or comment out the `html_theme` setting in conf.py when testing the build
locally.

The target of common interest is `make html`, though the other standard
sphinx targets are also available. Any output lands in the `_build/`
subdirectory, with the HTML output in particular landing in `_build/html/`.
