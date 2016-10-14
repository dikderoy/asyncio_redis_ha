# Redis High Availability Package for asyncio-redis

## Features

- Sentinel support ontop of asyncio-redis:
    - role
    - sentinels
    - slaves
    - get_master_addr_by_name
- Extended Redis support (versions 3.x)
    - role
    
- Fully tested

## Dependencies

Redis cluster with Sentinel solution requires `Redis 3.x`

This package uses and heavily depends on [`asyncio-redis`][1],
 because of the dependencies on package internals
 (due to required changes to support sentinel operations)
 requirement fixed at version `0.14.3`
 
I will manually update this dependency after ensuring that internals are compatible.

## Roadmap

- implement pool reinitialization on master connection loss
- add repeat/backoff wrapper as part of the package (coroutine or decorator)
- provide automated testing for failover scenarios

[1]: https://github.com/jonathanslenders/asyncio-redis

## User Guide

Usage is the very same as for `asyncio-redis` package Pool object,
except for initialization of an entry point
 
### Initialize a ConnectionManager

    config = HighAvailabilityConfig(
        cluster_name='mymaster',
        sentinels=[
            ('172.17.0.5', 26379),
            ('172.17.0.6', 26379),
            ('172.17.0.7', 26379)
        ]
    )
    
    c = self.pool_class(config, poolsize=poolsize, loop=self.loop)
    yield from c.discover()