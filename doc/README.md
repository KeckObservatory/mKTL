The sphinx documentation for mKTL is generated automatically upon any changes
to the main branch. The generated documentation is published here:

https://keckobservatory.github.io/mKTL

This documentation set uses sphinx and the Read the Docs theme; if being built
on a Debian-derived Linux distribution one might need to install the following
packages, or something similar:

	python3-myst-parser
	python3-sphinx
	python3-sphinx-rtd-theme

If the Read the Docs theme is not available on your platform you can comment
out the `html_theme` setting in conf.py when building the documentation locally.

The target of common interest is `make html`, though the other standard
sphinx targets are also available. Any output lands in the `_build/`
subdirectory, with the HTML output in particular landing in `_build/html/`.
