#! /usr/bin/env python3
# coding: utf8

import enum
import asyncio

class HTTPRequest:
    def __init__(self):
        self.data = b''
        self.request_line = b''
        self.header_buf = b''

        self.method = ''
        self.request_uri = ''
        self.http_version = ''
        self.headers = []
        self.body_buf = b''
        self._transport = None
        self._protocol = None
    
    async def recv_body_chunk(self):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._protocol.add_buffer_updated_callback(lambda b: future.set_result(None))
        await future

