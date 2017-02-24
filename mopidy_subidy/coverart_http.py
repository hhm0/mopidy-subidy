from __future__ import absolute_import, unicode_literals

import os

import logging
import tornado.web
from mopidy import httpclient
from mopidy_subidy import subsonic_api
import mopidy_subidy

logger = logging.getLogger(__name__)

class CoverartRequestHandler(tornado.web.RequestHandler):
    def initialize(self, subsonic_api):
        self.subsonic_api = subsonic_api

    def get(self):
        a_id = self.get_argument('id')
        fetched = self.subsonic_api.get_raw_coverart_bin(a_id)
        if fetched is not None:
            # FIXME: this does not have the image's specific mimetype
            self.set_header('Content-Type', 'application/octet-stream')
            for chunk in iter(lambda: fetched.read(8192), ''):
                self.write(chunk)
        else:
            self.send_error()

def factory(config, core):
    sapi = subsonic_api.get_subsonic_api_with_config(config)
    return (
        ('/cover_art', CoverartRequestHandler, dict(subsonic_api=sapi)),
    )
