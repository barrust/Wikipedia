.. _api:

Wikipedia Documentation
***********************

Here you can find the full developer API for the wikipedia project.

Contents:

.. toctree::

   code

.. automodule:: wikipedia
  :members:

Functions and Classes
===============================

.. automodule:: wikipedia

  .. autofunction:: search(query, results=10, suggestion=False)

  .. autofunction:: suggest(query)

  .. autofunction:: summary(query, sentences=0, chars=0, auto_suggest=True, redirect=True)

  .. autofunction:: geosearch(latitude, longitude, title=None, results=10, radius=1000)

  .. autofunction:: categorymembers(category, results=10, subcategories=True)

  .. autofunction:: categorytree(category, depth=5)

  .. autofunction:: opensearch(query, results=10, redirect=False)

  .. autofunction:: prefexsearch(query, results=10)

  .. autofunction:: page

.. autoclass:: wikipedia.WikipediaPage
  :members:

.. autofunction:: wikipedia.languages

.. autofunction:: wikipedia.set_lang

.. autofunction:: wikipedia.set_rate_limiting

.. autofunction:: wikipedia.random

.. autofunction:: wikipedia.donate

.. autofunction:: wikipedia.clear_cache

.. autofunction:: wikipedia.reset_session

.. autofunction:: wikipedia.set_user_agent

.. autofunction:: wikipedia.get_user_agent

Exceptions
==========

.. automodule:: wikipedia.exceptions
  :members:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
