import asyncio

from asyncio_redis.protocol import MultiBulkReply
from asyncio_redis.replies import ListReply, DictReply


class NestedListReply(ListReply):
    @asyncio.coroutine
    def aslist(self):
        """ Return the result as a Python ``list[list]``. """
        final = []
        data = yield from super().aslist()
        """:type data : list"""
        for x in data:
            if isinstance(x, MultiBulkReply):
                nested = yield from ListReply(x).aslist()
                final.append(nested)
            else:
                final.append(x)
        return final


class NestedDictReply(ListReply):
    @asyncio.coroutine
    def aslist(self):
        """ Return the result as a Python ``list[dict]``. """
        final = []
        data = yield from super().aslist()
        """:type data : list"""
        for x in data:
            if isinstance(x, MultiBulkReply):
                x = DictReply(x)
                nested = yield from x.asdict()
                final.append(nested)
            else:
                final.append(x)
        return final
