#! /usr/bin/env python3
# coding: utf8

import sys
import asyncio
import http
import logging
import socket
import datetime

logger = logging.getLogger('connproxy')
fmtr = logging.Formatter(
    '[%(asctime)s] %(levelname)-8s <%(process)d:%(threadName)s> '
    '%(filename)s:%(lineno)d %(funcName)s - %(message)s'
)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(fmtr)
logger.addHandler(h)
logger.setLevel(logging.DEBUG)

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
    peerinfo = writer.get_extra_info('peername')
    while True:
        if writer.is_closing():
            break
        if reader.at_eof():
            break
        buf = await reader.read(1024)
        if len(buf) > 0:
            writer.write(buf)
            await writer.drain()
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
        await asyncio.gather(stream_copy(reader, upstream_writer), stream_copy(upstream_reader, writer), loop=loop)
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



    
    
         
