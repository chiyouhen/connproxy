#! /usr/bin/env python3
# coding: utf8

import sys
import asyncio
import http
import logging
import socket
import datetime
import heapq

logger = logging.getLogger('connproxy')
fmtr = logging.Formatter(
    '[%(asctime)s] %(levelname)-8s <%(process)d:%(threadName)s> '
    '%(filename)s:%(lineno)d %(funcName)s - %(message)s'
)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(fmtr)
logger.addHandler(h)
logger.setLevel(logging.DEBUG)

class Error(Exception):
    pass

class HTTPError(Error):
    def __init__(self, status_code):
        self.status_code = status_code

    def __str__(self):
        return 'HTTP {} error, {}'.format(self.status_code.value, self.status_code.phrase)

class HTTPInvalidHeaderError(HTTPError):
    pass

class HTTPInvalidRequestError(HTTPError):
    def __init__(self):
        super().__init__(http.HTTPStatus.BAD_REQUEST)

class Connection:
    @classmethod
    async def connect(cls, host, port, *, conn_timeout=None, **kwargs):
        loop = kwargs['loop'] if 'loop' in kwargs else asyncio.get_event_loop()
        if conn_timeout is None:
            conn_timeout = timeout
        if conn_timeout is None:
            reader, writer = asyncio.open_connection(host, port)
        else:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=conn_timeout.total_seconds())
        conn = cls(reader, writer, **kwargs)
        return conn

    def __init__(self, reader, writer, *, timeout=None, read_timeout=None, write_timeout=None, buf_size=4096, loop=None):
        self.reader = reader
        self.writer = writer
        self.timeout = timeout
        self.read_timeout = read_timeout if not read_timeout is None else timeout
        self.write_timeout = write_timeout if not write_timeout is None else timeout
        self.buf_size = buf_size
        self.loop = loop if not loop is None else asyncio.get_event_loop()

    async def read(self, n=-1):
        if self.read_timeout is None:
            return await self.reader.read(n)
        else:
            return await asyncio.wait_for(self.reader.read(n), timeout=self.read_timeout.total_seconds(), loop=self.loop)

    def write(self, buf):
        return self.writer.write(buf)

    async def flush(self):
        if self.write_timeout is None:
            return await self.writer.drain()
        else:
            return await asyncio.wait_for(self.writer.drain(), timeout=self.write_timeout.total_seconds(), loop=self.loop)

    async def clean_write(self, buf):
        self.write(buf)
        return await self.flush()

    def close(self):
        self.writer.close()

class HTTPHeader:
    def __init__(self, key, value):
        self.key_raw = key
        self.key = self.__key_convert(key)
        self.value = self.__type_convert(value)

    def __type_convert(self, v):
        if isinstance(v, str):
            v = v.encode()
        elif not isinstance(v, bytes):
            v = f'{v}'.encode()

        return v

    def __key_convert(self, k):
        k = self.__type_convert(k)
        return k.replace(b'-', b'_').lower()

class HTTPHeaders(list):
    def __init__(self, data=None):
        super().__init__([])
        if data is None:
            return 

        elif isinstance(data, dict):
            self.__init_from_dict(data)
        elif isinstance(data, list):
            self.__init_from_list(data)
        elif isinstance(data, bytes):
            self.__init_from_bytes(data)
        elif isinstance(data, str):
            self.__init_from_str(data)

    def __init_from_dict(self, data):
        for k in data:
            h = HTTPHeader(k, data[k])
            self.append(h)

    def __init_from_dict(self, data):
        for k, v in data:
            h = HTTPHeader(k, v)
            self.append(h)

    def __init__from_bytes(self, data):
        lines = data.split(b'\r\n')
        for l in lines:
            a = l.split(b':', 1)
            if len(a) != 2:
                raise HTTPInvalidHeaderError()
            k = k.strip()
            h = HTTPHeader(k, v.strip())
            self.append(h)

    def __init_from_str(self, data):
        self.__init__from_types(data.encode())


class HTTPRequest:
    def __init__(self, request_url, method='GET', headers=None, body=None, connection=None):
        self.request_url = request_url
        self.url = urllib.parse.urlparse(request_url, allow_fragments=False)
        self.headers = HTTPHeaders(headers)
        self.method = method
        if not isinstance(body, bytes):
            self.body = body.encode()
        else:
            self.body = body
        self.connection = connection

class HTTP10Connection(Connection):
    def __init__(self, header_bufsize=4096, chunk_bufsize=4096, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_bufsize = header_bufsize
        self.chunk_bufsize = chunk_bufsize
        self.header_received = False
        self.unparsed_header = b''
        self.body = b''
        self.headers = {}
        self.data = b''

    async def recv_header(self):
        if self.header_received:
            return self.headers

        buf = self.read(self.header_bufsize)
        self.data += buf
        if not b'\r\n\r\n' in data:
            raise HTTPInvalidRequestError()

        self.unparsed_header, self.body = self.data.split(b'\r\n\r\n')
            

        
        
        
        


async def send_response(reader, writer, status_code):
    writer.write(
        b'HTTP/1.0 %d %s\r\nProxy-Agent: connproxy\r\n\r\n' % (
            status_code.value, status_code.phrase.encode()
        )
    )
    await writer.drain()

async def send_badrequest(reader, writer):
    await send_response(reader, writer, http.HTTPStatus.BAD_REQUEST)

async def send_connected(reader, writer):
    await send_response(reader, writer, http.HTTPStatus.OK)

async def send_timeout(reader, writer):
    await send_response(reader, writer, http.HTTPStatus.GATEWAY_TIMEOUT)

async def send_connfailed(reader, writer):
    await send_response(reader, writer, http.HTTPStatus.BAD_GATEWAY)

async def finish_request(reader, writer):
    await writer.drain()
    writer.close()
    await writer.wait_closed() 

async def stream_copy(reader, writer):
    loop = asyncio.get_running_loop()
    peerinfo = writer.get_extra_info('peername')
    while True:
        if writer.is_closing():
            break
        if reader.at_eof():
            break
        buf = await asyncio.wait_for(reader.read(1024), timeout=10, loop=loop)
        if len(buf) > 0:
            writer.write(buf)
            await asyncio.wait_for(writer.drain(), timeout=10, loop=loop)
            logger.debug('{} byte send to {}'.format(len(buf), peerinfo))
    logger.debug('nothing to send to {}, iocopy finished'.format(peerinfo))

async def on_connected(reader, writer):
    request_start = datetime.datetime.now()
    client_peername = writer.get_extra_info('peername')
    logger.debug('new connection comes: {}'.format(client_peername))
    loop = asyncio.get_running_loop()
    
    request_header = await reader.read(4096)
    protocol_line = request_header.split(b'\r\n')[0]
    a = protocol_line.split()

    if len(a) != 3:
        await send_badrequest(reader, writer)
        await finish_request(reader, writer)
        logger.error('invalid protocol_line "{}"'.format(protocol_line))
        return

    method, addr, protocol_version = a[0], a[1], a[2]
    if method != b'CONNECT':
        await send_badrequest(reader, writer)
        await finish_request(reader, writer)
        logger.error('invalid method {}'.format(method))
        return

    if b':' in addr:
        host, port = addr.split(b':')
        host = host.decode()
        port = int(port)
    else:
        host = addr.decode()
        port = 80

    hostinfos = await loop.getaddrinfo(host, port)
    ipaddr, port = hostinfos[0][4]
    conn_fut = asyncio.open_connection(ipaddr, port, ssl=False, loop=loop)
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(conn_fut, timeout=10, loop=loop)
    except asyncio.TimeoutError as e:
        await send_timeout(reader, writer)
        await finish_request(reader, writer)
        logger.error('connect {}:{} timeout'.format(ipaddr, port))
        return 
    except ConnectionRefusedError as e:
        await send_connfailed(reader, writer)
        await finish_request(reader, writer)
        logger.error('connect {}:{} failed, {}'.format(ipaddr, port, e))
        return
        
    await send_connected(reader, writer)
    logger.debug('connection established with {}:{}'.format(ipaddr, port))
    try:
        try:
            await asyncio.gather(stream_copy(reader, upstream_writer), stream_copy(upstream_reader, writer), loop=loop)
        except asyncio.TimeoutError as e:
            logger.error('socket timeout while processing transfer')
        writer.close()
        upstream_writer.close()
        await asyncio.gather(writer.wait_closed(), upstream_writer.wait_closed(), loop=loop)
    except ConnectionError as e:
        logger.error('connection error while processing transfer')
    request_finished = datetime.datetime.now()
    logger.info('{} "{}" {}:{} cost:{}(s)'.format(
        client_peername, protocol_line.decode(), ipaddr, port, 
        (request_finished-request_start).total_seconds()
    ))

loop = asyncio.get_event_loop()
coro = asyncio.start_server(on_connected, '127.0.0.1', 11113, loop=loop)
server = loop.run_until_complete(coro)
loop.run_forever()



    
    
         
