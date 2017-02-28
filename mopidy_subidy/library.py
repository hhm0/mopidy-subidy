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

    def browse_songs(self, album_id):
        return self.subsonic_api.get_songs_as_refs(album_id)

    def browse_albums(self, artist_id=None):
        return [Ref.directory(name=album.name, uri=album.uri) for album in self.subsonic_api.get_albums_as_refs(artist_id)]

    def browse_artists(self):
        return [Ref.directory(name=artist.name, uri=artist.uri) for artist in self.subsonic_api.get_artists_as_refs()]

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

    def lookup_playlist(self, playlist_id):
        return self.subsonic_api.get_playlist_as_playlist(playlist_id).tracks

    def browse(self, browse_uri):
        vdir_templates = [
            # ("root", <no name>)
            ("rootdirs", "Directories"),
            ("artists", "Artists"),
            ("albums", "Albums"),
        ]
        vdirs = dict((template[0], dict(id=template[0], name=template[1])) for template in vdir_templates)
        if browse_uri == uri.ROOT_URI:
            root_vdirs = sorted((vdirs[vdir_name] for vdir_name in ["rootdirs", "artists", "albums"]), key=lambda a: a["name"])
            return [Ref.directory(name=vdir["name"], uri=uri.get_vdir_uri(vdir["id"])) for vdir in root_vdirs]
        elif browse_uri == uri.get_vdir_uri("rootdirs"):
            return self.browse_rootdirs()
        elif browse_uri == uri.get_vdir_uri("artists"):
            return self.browse_artists()
        elif browse_uri == uri.get_vdir_uri("albums"):
            return self.browse_albums()
        else:
            uri_type = uri.get_type(browse_uri)
            if uri_type == uri.DIRECTORY:
                return self.browse_diritems(uri.get_directory_id(browse_uri))
            elif uri_type == uri.ARTIST:
                return self.browse_albums(uri.get_artist_id(browse_uri))
            elif uri_type == uri.ALBUM:
                return self.browse_songs(uri.get_album_id(browse_uri))
            else:
                return []

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
        if type == uri.PLAYLIST:
            return self.lookup_playlist(uri.get_playlist_id(lookup_uri))

    def lookup(self, uri=None, uris=None):
        if uris is not None:
            return dict((uri, self.lookup_one(uri)) for uri in uris)
        if uri is not None:
            return self.lookup_one(uri)
        return None

    def refresh(self, uri):
        pass

    def search_uri_iter(self, lookup_uri, include_self=True):
        type = uri.get_type(lookup_uri)
        if type == uri.ARTIST:
            artistid = uri.get_artist_id(lookup_uri)
            artist = self.subsonic_api.get_artist_by_id(artistid)
            if artist is not None:
                if include_self:
                    yield (uri.ARTIST, artist)
                for i in self.subsonic_api.get_albums_as_albums(artistid):
                    yield (uri.ALBUM, i)
                for i in self.subsonic_api.get_artist_as_songs_as_tracks_iter(artistid):
                    yield (uri.SONG, i)
        elif type == uri.ALBUM:
            albumid = uri.get_album_id(lookup_uri)
            album = self.subsonic_api.get_album_by_id(albumid)
            if album is not None:
                if include_self:
                    yield (uri.ALBUM, album)
                for i in self.lookup_album(albumid):
                    yield (uri.SONG, i)
        elif type == uri.DIRECTORY:
            for i in self.lookup_directory(uri.get_directory_id(lookup_uri)):
                yield (uri.SONG, i)
        elif type == uri.SONG:
            if include_self:
                song = self.subsonic_api.get_song_by_id(uri.get_song_id(lookup_uri))
                if song:
                    yield (uri.SONG, song)
        # TODO: playlist uri supporting

    def finds_to_dict(self, finds):
        artists = []
        albums = []
        tracks = []
        for found in finds:
            if found[0] == uri.ARTIST:
                artists.append(found[1])
            elif found[0] == uri.ALBUM:
                albums.append(found[1])
            elif found[0] == uri.SONG:
                tracks.append(found[1])
        return dict(artists=artists, albums=albums, tracks=tracks)

    def search_by_artist_album_and_track(self, artist_name, album_name, track_name):
        tracks = self.search_by_artist_and_album(artist_name, album_name)
        track = next(item for item in tracks.tracks if track_name in item.name)
        return SearchResult(tracks=[track])

    def search_by_artist_and_album(self, artist_name, album_name):
        artists = self.subsonic_api.get_raw_artists()
        artist = next(item for item in artists if artist_name in item.get('name'))
        albums = self.subsonic_api.get_raw_albums(artist.get('id'))
        album = next(item for item in albums if album_name in item.get('title'))
        return SearchResult(tracks=self.subsonic_api.get_songs_as_tracks(album.get('id')))

    def get_distinct(self, field, query):
        search_result = self.search(query)
        if not search_result:
            return []
        if field == 'track' or field == 'title':
            return [track.name for track in (search_result.tracks or [])]
        if field == 'album':
            return [album.name for album in (search_result.albums or [])]
        if field == 'artist':
            if not search_result.artists:
                return [artist.name for artist in self.browse_artists()]
            return [artist.name for artist in search_result.artists]

    def search(self, query=None, uris=None, exact=False):
        if 'artist' in query and 'album' in query and 'track_name' in query:
            return self.search_by_artist_album_and_track(query.get('artist')[0], query.get('album')[0], query.get('track_name')[0])
        if 'artist' in query and 'album' in query:
            return self.search_by_artist_and_album(query.get('artist')[0], query.get('album')[0])
        if 'artist' in query:
            return self.subsonic_api.find_as_search_result(query.get('artist')[0])
        if 'any' in query:
            return self.subsonic_api.find_as_search_result(query.get('any')[0])
        if 'uri' in query:
            return SearchResult(
                **self.finds_to_dict(self.search_uri_iter(query.get('uri')[0])))
        if 'any' in query:
            q = query.get('any')[0]
            return SearchResult(
                uri=uri.get_search_uri(q),
                **self.finds_to_dict(self.subsonic_api.find_iter(q)))
        return SearchResult(artists=self.subsonic_api.get_artists_as_artists())

