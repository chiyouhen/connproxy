#! /usr/bin/env python3
# coding: utf8

import enum

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
        self.protocol = None

class Handler:
    def __init__(self, request):
        self.request = request

    async def execute(self):
        return 

class HandlerNotFound(Handler):
    async def execute(self):
        
        
    
