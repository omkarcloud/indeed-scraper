"""Response cache hook used by indeed/fetch.py.

The hosted API keeps responses in a database; this package keeps them in
memory only (indeed/fetch.py already memoizes shared payloads for 10
minutes), so the call simply runs."""


def cached_call(namespace, data, fn, ttl, cache=True):
    """Run fn(**data). Same signature as the hosted cache."""
    return fn(**data)
