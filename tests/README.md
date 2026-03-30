The tests here are expecting to be invoked via `pytest`. This will inspect
all test_*.py files in the local directory, including any subdirectories,
and invoke all defined tests discovered in this fashion. The simplest
invocation requires no arguments::

    pytest

If you only want to specify a subset of tests to run, you can do so; one
straightforward path is to select a file containing tests of interest::

    pytest ./test_items.py

pytest has a long list of ways it can be invoked. One report that may be
of particular interest is test coverage; the simplest invocation with a
summary of coverage would be::

    pytest --cov=mktl

You can also request a complete breakdown listing which sections of
code are not covered::

    pytest --cov=mktl --cov-report term-missing

The other `--cov-report` options, such as the HTML-formatted report, can
provide additional context beyond just the line numbers. It's worth remembering
that 100% test coverage doesn't mean all the corner cases have been exercised--
it's important that the tests cover as many cases as possible, which generally
means any given line of code will be exercised many times, in many different
ways, depending on the inputs provided.
