#! /usr/bin/env python3
# coding: utf8

import sys
import asyncio
import http
import logging
import socket
import datetime
import heapq
import enum

from . import web

logger = logging.getLogger('connproxy')

class Stage(enum.IntEnum):
    NEW = enum.auto()
    CONNECTED = enum.auto()
    HEADER_RECEIVING = enum.auto()
    REWRITING = enum.auto()
    MATCHING_HANDLER = enum.auto()
    HANDLING = enum.auto()
    CLOSING = enum.auto()
    CLOSED = enum.auto()

class HTTPProtocol(asyncio.BufferedProtocol):
    def __init__(self, chunk_size=1, rewriter=None, handler=None):
        self.chunk_size = chunk_size
        self._data = b''
        self._buf = None
        self.buf = None
        self.transport = None
        self._stage = Stage.NEW
        self.request = None
        self.rewriter = rewriter
        self.router = router

    def connection_made(self, transport):
        self.transport = transport
        self._stage = Stage.CONNECTED
        peername = self.transport.get_extra_info('peername')
        logger.info(f'Connection from {peername}')

    def get_buffer(self, sizehint=-1):
        if sizehint == -1:
            sizehint = self.chunk_size

        buf = bytearray(sizehint)
        buf_view = memoryview(buf)
        self._buf = buf_view[:sizehint]
        return self._buf

    def write_header(self):
        response_line = f'HTTP/1.0 {self.request.status} {http.HTTPStatus(self.request.status).phrase}\r\n'.encode()
        self.transport.write(response_line)
        for k, v in self.request.res_headers:
            self.transport.write(f'{k}: {v}\r\n'.encode())
        self.transport.write(b'\r\n')
        self.request.header_written = True

    def _post_handling(self, future):
        self._stage = Stage.CLOSING

    def handle(self):
        loop = asyncio.get_event_loop()
        future = loop.ensure_future(self.handler.execute())
        future.add_done_callback(self._post_handling)

    def _handle(self):
        body = b'STATUS OK\r\n'
        self.request.status = http.HTTPStatus.OK
        self.request.res_headers.append(('Server', 'python.asyncio'))
        self.request.res_headers.append(('Content-Length', len(body)))
        self.write_header()
        self.transport.write(body)
        self.finalize_request()

    def create_request(self):
        request = web.HTTPRequest()
        request.data = self._data
        request.protocol = self
        self.request = request
        self._stage = Stage.HEADER_RECEIVING

    def finalize_request(self, status=http.HTTPStatus.OK):
        if self.request.header_written:
            self.transport.close()

        self.request.status = status
        self.write_header()
        logger.info(f'"{self.request.request_line.decode()}" {self.request.status}')
        self.transport.close()

    def recv_header(self):
        if not b'\r\n\r\n' in self._data:
            return

        header_buf, body_buf = self._data.split(b'\r\n\r\n', 1)
        self.request.body = body_buf
        lines = header_buf.split(b'\r\n')
        logger.debug(f'lines: {lines}')
        request_line = lines[0]
        a = request_line.split()
        if len(a) != 3:
            self.finalize_request(http.HTTPStatus.BAD_REQUEST)

        self.request.method = a[0].decode()
        self.request.request_uri = a[1].decode()
        self.request.http_version = a[2].decode()
        logger.debug(f'request_line: {request_line}')

        for l in lines[1:]:
            logger.debug(f'header line: {l}')
            k, v = l.split(b':', 1)
            self.request.headers.append((k.decode().strip(), v.decode().strip()))

        self._stage = Stage.REWRITING

    def recv_body(self):
        self.request.body += self.buf

    async def recv_body_chunk(self):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.add_buffer_updated_future(future)
        return await future

    def rewrite(self):
        if not self.rewriter is None:
            self.rewriter.execute(self.request)
        self._stage = Stage.MATCHING_HANDLER

    def match_handler(self):
        if not self.router is None:
            Handler = self.router.execute(self.request)
            self.handler = Handler(self.request, self.transport)
        else:
            self.handler = web.HandlerNotFound(self.request, self.transport)
        self._stage = Stage.HANDLING

    def buffer_updated(self, nbytes):
        self.buf = bytes(self._buf)
        self._buf = None
        self._data += self.buf[:nbytes]
        logger.debug(f'stage: {self._stage.name}')
        if self._stage == Stage.CONNECTED:
            self.create_request()

        if self._stage == Stage.HEADER_RECEIVING:
            self.recv_header()

        if self._stage == Stage.BODY_RECEIVING:
            self.recv_body()

        if self._stage == Stage.HANDLING:
            self.handle()

        if self._stage == Stage.CLOSING:
            self.finalize_request()

    def eof_received(self):
        logger.debug(f'eof_received')
        if self._stage == Stage.BODY_RECEIVING:
            self._stage = Stage.HANDLING
       

