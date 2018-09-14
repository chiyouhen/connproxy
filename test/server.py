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

import connproxy

if __name__ == '__main__':
    logger = logging.getLogger('connproxy')
    fmtr = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s <%(process)d:%(threadName)s> '
        '%(filename)s:%(lineno)d %(funcName)s - %(message)s'
    )
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmtr)
    logger.addHandler(h)
    logger.setLevel(logging.DEBUG)
    loop = asyncio.get_event_loop()
    co = loop.create_server(connproxy.HTTPProtocol, '127.0.0.1', 8999)
    server = loop.run_until_complete(co)
    try:
        loop.run_forever()
    except KeyboardInterrupt as e:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
     

