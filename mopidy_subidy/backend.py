from mopidy_subidy import library, playback, playlists, subsonic_api
from mopidy import backend, httpclient
import pykka

class SubidyBackend(pykka.ThreadingActor, backend.Backend):
    def __init__(self, config, audio):
        super(SubidyBackend, self).__init__()
        self.subsonic_api = subsonic_api.get_subsonic_api_with_config(config)
        self.library = library.SubidyLibraryProvider(backend=self)
        self.playback = playback.SubidyPlaybackProvider(audio=audio, backend=self)
        self.playlists = playlists.SubidyPlaylistsProvider(backend=self)
        self.uri_schemes = ['subidy']
