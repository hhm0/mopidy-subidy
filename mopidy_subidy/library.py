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
        song = self.subsonic_api.get_song_by_id(song_id)
        if song is None:
            return []
        else:
            return [song]

    def lookup_album(self, album_id):
        return self.subsonic_api.get_songs_as_tracks(album_id)

    def lookup_artist(self, artist_id):
        return list(self.subsonic_api.get_artist_as_songs_as_tracks_iter(artist_id))

    def lookup_directory(self, directory_id):
        return list(self.subsonic_api.get_recursive_dir_as_songs_as_tracks_iter(directory_id))

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
            return self.lookup_song(uri.get_song_id(lookup_uri))
        # TODO: uri.PLAYLIST

    def lookup(self, uri=None, uris=None):
        if uris is not None:
            return dict((uri, self.lookup_one(uri)) for uri in uris)
        if uri is not None:
            return self.lookup_one(uri)
        return None

    def refresh(self, uri):
        pass

    def search_uri(self, lookup_uri):
        type = uri.get_type(lookup_uri)
        if type == uri.ARTIST:
            artistid = uri.get_artist_id(lookup_uri)
            artist = self.subsonic_api.get_artist_by_id(artistid)
            if artist is not None:
                albums = self.subsonic_api.get_albums_as_albums(artistid)
                tracks = self.lookup_artist(artistid)
                return dict(artists=[artist], albums=albums, tracks=tracks)
        elif type == uri.ALBUM:
            albumid = uri.get_album_id(lookup_uri)
            album = self.subsonic_api.get_album_by_id(albumid)
            if album is not None:
                tracks = self.lookup_album(albumid)
                return dict(albums=[album], tracks=tracks)
        elif type == uri.DIRECTORY:
            dirsongs =  self.lookup_directory(uri.get_directory_id(lookup_uri))
            return dict(tracks=dirsongs)
        elif type == uri.SONG:
            songlist = self.lookup_song(uri.get_song_id(lookup_uri))
            return dict(tracks=songlist)
        # TODO: playlist uri supporting
        return {}

    def search(self, query=None, uris=None, exact=False):
        if 'uri' in query:
            return SearchResult(**self.search_uri(query.get('uri')[0]))
        if 'any' in query:
            return self.subsonic_api.find_as_search_result(query.get('any')[0])
