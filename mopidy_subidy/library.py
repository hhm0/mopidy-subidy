from mopidy import backend, models
from mopidy.models import Ref, SearchResult
from mopidy_subidy import uri

import logging
logger = logging.getLogger(__name__)

class SubidyLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri=uri.ROOT_URI, name='Subsonic')

    def __init__(self, *args, **kwargs):
        super(SubidyLibraryProvider, self).__init__(*args, **kwargs)
        self.subsonic_api = self.backend.subsonic_api

    def browse_songs(self,album_id):
        return self.subsonic_api.get_songs_as_refs(album_id)

    def browse_albums(self, artist_id):
        return self.subsonic_api.get_albums_as_refs(artist_id)

    def browse_artists(self):
        return self.subsonic_api.get_artists_as_refs()

    def browse_rootdirs(self):
        return self.subsonic_api.get_rootdirs_as_refs()

    def browse_diritems(self, directory_id):
        return self.subsonic_api.get_diritems_as_refs(directory_id)

    def lookup_song(self, song_id):
        return self.subsonic_api.get_song_by_id(song_id)

    def lookup_album(self, album_id):
        return self.subsonic_api.get_songs_as_tracks(album_id)

    def lookup_artist(self, artist_id):
        return self.subsonic_api.get_artist_as_songs_as_tracks(artist_id)

    def lookup_directory(self, directory_id):
        return self.subsonic_api.get_diritems_as_tracks(directory_id)

    def browse(self, browse_uri):
        if browse_uri == uri.ROOT_URI:
            return self.browse_rootdirs()
        else:
            return self.browse_diritems(uri.get_directory_id(browse_uri))

    def lookup_one(self, lookup_uri):
        type = uri.get_type(lookup_uri)
        if type == uri.ARTIST:
            return self.lookup_artist(uri.get_artist_id(lookup_uri))
        if type == uri.ALBUM:
            return self.lookup_album(uri.get_album_id(lookup_uri))
        if type == uri.DIRECTORY:
            return self.lookup_directory(uri.get_directory_id(lookup_uri))
        if type == uri.SONG:
            return [self.lookup_song(uri.get_song_id(lookup_uri))]

    def lookup(self, uri=None, uris=None):
        if uris is not None:
            return dict((uri, self.lookup_one(uri)) for uri in uris)
        if uri is not None:
            return self.lookup_one(uri)
        return None

    def refresh(self, uri):
        pass

    def search_uri(self, query):
        type = uri.get_type(lookup_uri)
        if type == uri.ARTIST:
            artist = self.lookup_artist(uri.get_artist_id(lookup_uri))
            if artist is not None:
                return SearchResult(artists=[artist])
        elif type == uri.ALBUM:
            album = self.lookup_album(uri.get_album_id(lookup_uri))
            if album is not None:
                return SearchResult(albums=[album])
        elif type == uri.SONG:
            song = self.lookup_song(uri.get_song_id(lookup_uri))
            if song is not None:
                return SearchResult(tracks=[song])
        return None

    def search(self, query=None, uris=None, exact=False):
        if 'uri' in query:
            return self.search_uri(query.get('uri')[0])
        if 'any' in query:
            return self.subsonic_api.find_as_search_result(query.get('any')[0])

    def get_coverart_image(self, a_uri):
        utype = uri.get_type(a_uri)
        if utype == uri.ARTIST:
            coverart_item_id = self.subsonic_api.coverart_item_id_by_artist_id(uri.get_artist_id(a_uri))
        elif utype == uri.ALBUM:
            coverart_item_id = self.subsonic_api.coverart_item_id_by_album_id(uri.get_album_id(a_uri))
        elif utype == uri.SONG:
            coverart_item_id = self.subsonic_api.coverart_item_id_by_song_id(uri.get_song_id(a_uri))
        elif utype == uri.DIRECTORY:
            coverart_item_id = self.subsonic_api.coverart_item_id_by_directory_id(uri.get_directory_id(a_uri))
        else:
            return []
        if coverart_item_id is not None:
            image_uri = self.subsonic_api.get_coverart_image_by_id(coverart_item_id)
            if image_uri is not None:
                return [image_uri]
            else:
                return []
        else:
            return []

    def get_images(self, uris):
        return dict((a_uri, self.get_coverart_image(a_uri)) for a_uri in uris)
