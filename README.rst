Redis High Availability Package for asyncio-redis
=================================================

High Availability package and Sentinel client for the `PEP 3156`_ Python event loop.

This package is a wrapper/plugin for asyncio-redis_ asynchronous, non-blocking client for a
Redis server. It depends on asyncio (PEP 3156) and therefor it requires Python
3.3 or 3.4. If you're new to asyncio, it can be helpful to check out
`the asyncio documentation`_ first.

Features
--------

- Sentinel support ontop of asyncio-redis:

  - role
  - sentinels
  - slaves
  - get_master_addr_by_name

- Extended Redis support (versions 3.x)

  - role

- Mostly tested

  - all tests from asyncio-redis_ are green
  - new functionality covered and guaranteed to run in same conditions
  - failover scenarios tested manually


Dependencies
------------

Redis cluster with Sentinel solution requires ``Redis 3.x``

This package uses and heavily depends on asyncio-redis_,
because of the dependencies on package internals
(due to required changes to support sentinel operations)
currently requirement fixed at version ``0.14.3``

I will manually update this dependency after ensuring that internals are compatible.

Roadmap
-------

- implement pool reinitialization on master connection loss
- add repeat/backoff wrapper as part of the package (coroutine or decorator)
- provide automated testing for failover scenarios
- implement preemptive connection reconfiguration
  (instant failover detection based on channel events from Sentinel daemon)
- hiredis support



User Guide
----------

Usage is the very same as for asyncio-redis_ package Pool object,
except for initialization of an entry point

**Initialize a ConnectionManager**

.. code:: python

    c = yield from ConnectionManager.create(
            cluster_name='mymaster',
            sentinels=[
                ('172.17.0.4', 26379),
                ('172.17.0.6', 26379),
                ('172.17.0.7', 26379)
            ],
            poolsize=5
    )
    #  start using just like asyncio-redis
    yield from c.set('key', 'value')


.. _asyncio-redis: https://github.com/jonathanslenders/asyncio-redis
.. _the asyncio documentation: http://docs.python.org/dev/library/asyncio.html
.. _PEP 3156: http://legacy.python.org/dev/peps/pep-3156/