from __future__ import absolute_import, unicode_literals

import os

import logging
import tornado.web
import requests
import trequests
import tornalet
from mopidy import httpclient
from mopidy_subidy import subsonic_api
import mopidy_subidy

logger = logging.getLogger(__name__)

trequests.setup_session()

class CoverartRequestHandler(tornado.web.RequestHandler):
    def initialize(self, config, subsonic_api):
        self.proxy_formatted = httpclient.format_proxy(config['proxy'])
        self.subsonic_api = subsonic_api

    @tornalet.tornalet
    def get(self):
        a_id = self.get_argument('id')
        proxies = dict(http=self.proxy_formatted, https=self.proxy_formatted)
        useragent = httpclient.format_user_agent('{name}/{ver}'.format(name=mopidy_subidy.SubidyExtension.dist_name, ver=mopidy_subidy.__version__))
        censored_url = self.subsonic_api.get_censored_coverart_image_uri(a_id)
        logger.debug("Loading cover art from subsonic with url: '%s'" % censored_url)
        url = self.subsonic_api.get_coverart_image_uri(a_id)
        try:
            fetched = requests.get(url, headers={'user-agent': useragent}, proxies=proxies, stream=True)
            self.set_header('Content-Type', fetched.headers.get('content-type', 'application/octet-stream'))
            for chunk in fetched.iter_content(chunk_size=8192):
                self.write(chunk)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading cover art image.')

def factory(config, core):
    sapi = subsonic_api.get_subsonic_api_with_config(config)
    return (
        ('/cover_art', CoverartRequestHandler, dict(config=config, subsonic_api=sapi)),
    )
