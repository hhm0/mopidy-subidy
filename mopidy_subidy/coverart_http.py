from __future__ import absolute_import, unicode_literals

import os

import logging
import concurrent.futures
import tornado.web
import tornado.gen
import tornado.concurrent
import requests
from mopidy import httpclient
from mopidy_subidy import subsonic_api
import mopidy_subidy

logger = logging.getLogger(__name__)

class CoverartRequestHandler(tornado.web.RequestHandler):
    executor = concurrent.futures.ThreadPoolExecutor(10)

    def initialize(self, config, subsonic_api):
        self.proxy_formatted = httpclient.format_proxy(config['proxy'])
        self.subsonic_api = subsonic_api

    @tornado.concurrent.run_on_executor
    def _get_data(self, a_id): # from https://gist.github.com/methane/2185380#gistcomment-1301483
        proxies = dict(http=self.proxy_formatted, https=self.proxy_formatted)
        useragent = httpclient.format_user_agent('{name}/{ver}'.format(name=mopidy_subidy.SubidyExtension.dist_name, ver=mopidy_subidy.__version__))
        censored_url = self.subsonic_api.get_censored_coverart_image_uri(a_id)
        logger.debug("Loading cover art from subsonic with url: '%s'" % censored_url)
        url = self.subsonic_api.get_coverart_image_uri(a_id)
        try:
            fetched = requests.get(url, headers={'user-agent': useragent}, proxies=proxies)
            return fetched
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading cover art image.')
            raise tornado.web.HTTPError()

    @tornado.gen.coroutine
    def get(self):
        a_id = self.get_argument('id')
        fetched = yield self._get_data(a_id)
        self.set_header('Content-Type', fetched.headers.get('content-type', 'application/octet-stream'))
        self.write(fetched.content)

def factory(config, core):
    sapi = subsonic_api.get_subsonic_api_with_config(config)
    return (
        ('/cover_art', CoverartRequestHandler, dict(config=config, subsonic_api=sapi)),
    )
