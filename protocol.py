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

logger = logging.getLogger('connproxy')

class Stage(enum.IntEnum):
    NEW = enum.auto()
    CONNECTED = enum.auto()
    HEADER_RECEIVING = enum.auto()
    HANDLING = enum.auto()
    RESPONSE_WRITING = enum.auto()
    CLOSING = enum.auto()
    CLOSED = enum.auto()

class HTTPRequest:
    def __init__(self):
        self.data = b''
        self.request_line = b''
        self.method = ''
        self.request_uri = ''
        self.http_version = ''
        self.headers = []
        self.body = ''
        self.transport = None
        self.status = 0
        self.res_headers = []
        self.header_written = False
    
class HTTPProtocol(asyncio.BufferedProtocol):
    def __init__(self, chunk_size=4096):
        self.chunk_size = chunk_size
        self._data = b''
        self._buf = None
        self.transport = None
        self._stage = Stage.NEW
        self.request = None

    def connection_made(self, transport):
        self.transport = transport
        self._stage = Stage.CONNECTED
        peername = self.transport.get_extra_info('peername')
        logger.info(f'Connection from {peername}')

    def get_buffer(self, sizehint=-1):
        if sizehint == -1:
            sizehint = self.chunk_size

        self._buf = memoryview(b' ' * sizehint)
        return self._buf

    def write_header(self):
        response_line = b'{self.request.status} {http.HTTPStatus(self.request.status).phrase}\r\n'
        self.transport.write(response_line)
        for k, v in self.res_headers:
            self.transport.write(b'{k}: {v}\r\n')
        self.transport.write(b'\r\n')
        self.request.header_written = True

    def handle(self):
        self.request.status = http.HTTPStatus.OK
        self.request.res_headers.append(('Server', 'python.asyncio'))
        self.write_header()
        self.finalize_request()

    def create_request(self):
        request = HTTPRequest()
        request.data = self._data
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

        lines = self._data.split(b'\r\n')
        request_line = lines[0]
        a = request_line.split()
        if len(a) != 3:
            self.finalize_request(http.HTTPStatus.BAD_REQUEST)

        self.request.method = a[0]
        self.request.request_uri = a[1].decode()
        self.request.http_version = a[2].decode()

        for l in lines[1:]:
            k, v = l.split(b':', 1)
            self.request.headers.append((k.decode().strip(), v.decode().strip()))

        self._stage = Stage.HANDLING
   
    def buffer_updated(self, nbytes):
        buf = bytes(self._buf)
        self._buf = None
        self._data += buf[:nbytes]
        if self._stage == Stage.CONNECTED:
            self.create_request()

        elif self._stage == Stage.HEADER_RECEIVING:
            self.recv_header()

        elif self._stage == Stage.HANDLING:
            self.handle()

        elif self._stage == Stage.CLOSING:
            self.finalize_request()

if __name__ == '__main__':
    fmtr = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s <%(process)d:%(threadName)s> '
        '%(filename)s:%(lineno)d %(funcName)s - %(message)s'
    )
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmtr)
    logger.addHandler(h)
    logger.setLevel(logging.DEBUG)
    loop = asyncio.get_event_loop()
    co = loop.create_server(HTTPProtocol, '127.0.0.1', 8999)
    server = loop.run_until_complete(co)
    try:
        loop.run_forever()
    except KeyboardInterrupt as e:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
     

