from urlparse import urlparse
import libsonic
import logging
import itertools
import base64
import requests
from mopidy.models import Track, Album, Artist, Playlist, Ref, SearchResult, Image
from mopidy import httpclient
import mopidy_subidy
from mopidy_subidy import uri

logger = logging.getLogger(__name__)

RESPONSE_OK = u'ok'
UNKNOWN_SONG = u'Unknown Song'
UNKNOWN_ALBUM = u'Unknown Album'
UNKNOWN_ARTIST = u'Unknown Artist'
MAX_SEARCH_RESULTS = 100

ref_sort_key = lambda ref: ref.name

class SubsonicApi():
    def __init__(self, url, username, password, legacy_auth):
        parsed = urlparse(url)
        self.port = parsed.port if parsed.port else \
            443 if parsed.scheme == 'https' else 80
        base_url = parsed.scheme + '://' + parsed.hostname
        self.connection = libsonic.Connection(
            base_url,
            username,
            password,
            self.port,
            parsed.path + '/rest',
            legacyAuth=legacy_auth)
        self.url = url + '/rest'
        self.username = username
        self.password = password
        logger.info('Connecting to subsonic server on url %s as user %s' % (url, username))
        try:
            self.connection.ping()
        except Exception as e:
            logger.error('Unabled to reach subsonic server: %s' % e)
            exit()

    def get_song_stream_uri(self, song_id):
        template = '%s/stream.view?id=%s&u=%s&p=%s&c=mopidy&v=1.14'
        return template % (self.url, song_id, self.username, self.password)

    def get_censored_song_stream_uri(self, song_id):
        template = '%s/stream.view?id=%s&u=******&p=******&c=mopidy&v=1.14'
        return template % (self.url, song_id)

    def get_coverart_image_uri(self, aid):
        template = '%s/getCoverArt.view?id=%s&u=%s&p=%s&c=mopidy&v=1.14'
        return template % (self.url, aid, self.username, self.password)

    def get_censored_coverart_image_uri(self, aid):
        template = '%s/getCoverArt.view?id=%s&u=******&p=******&c=mopidy&v=1.14'
        return template % (self.url, aid)

    def find_raw(self, query, exclude_artists=False, exclude_albums=False, exclude_songs=False):
        try:
            response = self.connection.search3(
                query.encode('utf-8'),
                MAX_SEARCH_RESULTS if not exclude_artists else 0, 0,
                MAX_SEARCH_RESULTS if not exclude_albums else 0, 0,
                MAX_SEARCH_RESULTS if not exclude_songs else 0, 0)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when searching.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('searchResult2')

    def find_as_search_result(self, query, exclude_artists=False, exclude_albums=False, exclude_songs=False):
        result = self.find_raw(query)
        if result is None:
            return None
        return SearchResult(
            uri=uri.get_search_uri(query),
            artists=[self.raw_artist_to_artist(artist) for artist in result.get('artist') or []],
            albums=[self.raw_album_to_album(album) for album in result.get('album') or []],
            tracks=[self.raw_song_to_track(song) for song in result.get('song') or []])

    def get_raw_rootdirs(self):
        try:
            response = self.connection.getIndexes()
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of artists.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        letters = response.get('indexes').get('index')
        if letters is not None:
            artists = [artist for letter in letters for artist in letter.get('artist') or []]
            return artists
        logger.warning('Subsonic does not seem to have any artists in it\'s library.')
        return []

    def get_song_by_id(self, song_id):
        try:
            response = self.connection.getSong(song_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading song by id.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return self.raw_song_to_track(response.get('song')) if response.get('song') is not None else None

    def get_album_by_id(self, album_id):
        try:
            response = self.connection.getAlbum(album_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading album by id.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return self.raw_album_to_album(response.get('album')) if response.get('album') is not None else None

    def get_artist_by_id(self, artist_id):
        try:
            response = self.connection.getArtist(artist_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading artist by id.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return self.raw_artist_to_artist(response.get('artist')) if response.get('artist') is not None else None

    def get_coverart_image_by_id(self, a_id):
        censored_url = self.get_censored_coverart_image_uri(a_id)
        logger.debug("Loading cover art from subsonic with url: '%s'" % censored_url)
        url = self.get_coverart_image_uri(a_id)
        headers = {'user-agent': httpclient.format_user_agent('{name}/{ver}'.format(name=mopidy_subidy.SubidyExtension.dist_name, ver=mopidy_subidy.__version__))}
        proxies = dict(http=self.proxy_formatted, https=self.proxy_formatted)
        try:
            response = requests.get(url, headers=headers, proxies=proxies)
            uri_type = response.headers.get('content-type', 'application/octet-stream')
            b64_data = base64.b64encode(response.content)
            data_uri = ''.join(('data:', uri_type, ';base64,', b64_data))
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading cover art image.')
            return None
        return self.raw_imageuri_to_image(data_uri)

    def get_raw_playlists(self):
        try:
            response = self.connection.getPlaylists()
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of playlists.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        playlists = response.get('playlists').get('playlist')
        if playlists is None:
            logger.warning('Subsonic does not seem to have any playlists in it\'s library.')
            return []
        return playlists

    def get_raw_playlist(self, playlist_id):
        try:
            response = self.connection.getPlaylist(playlist_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading playlist.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('playlist')

    def get_raw_dir(self, parent_id):
        try:
            response = self.connection.getMusicDirectory(parent_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when listing content of music directory.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        directory = response.get('directory')
        if directory is not None:
            return directory.get('child')
        return None

    def get_raw_dirinfo(self, parent_id):
        try:
            response = self.connection.getMusicDirectory(parent_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading music directory.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('directory')

    def get_raw_artist(self, artist_id):
        try:
            response = self.connection.getArtist(artist_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading artist.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('artist')

    def get_raw_albums(self, artist_id):
        try:
            response = self.connection.getArtist(artist_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of albums.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        albums = response.get('artist').get('album')
        if albums is not None:
            return albums
        return []

    def get_raw_album(self, album_id):
        try:
            response = self.connection.getAlbum(album_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading album.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('album')

    def get_raw_songs(self, album_id):
        try:
            response = self.connection.getAlbum(album_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of songs in album.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        songs = response.get('album').get('song')
        if songs is not None:
            return songs
        return []

    def get_raw_song(self, song_id):
        try:
            response = self.connection.getSong(song_id)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading song.')
            return None
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return None
        return response.get('song')

    def get_albums_as_refs(self, artist_id):
        return [self.raw_album_to_ref(album) for album in self.get_raw_albums(artist_id)]

    def get_albums_as_albums(self, artist_id):
        return [self.raw_album_to_album(album) for album in self.get_raw_albums(artist_id)]

    def get_songs_as_refs(self, album_id):
        return [self.raw_song_to_ref(song) for song in self.get_raw_songs(album_id)]

    def get_songs_as_tracks(self, album_id):
        return [self.raw_song_to_track(song) for song in self.get_raw_songs(album_id)]

    def get_artists_as_refs(self):
        return [self.raw_artist_to_ref(artist) for artist in self.get_raw_artists()]

    def get_rootdirs_as_refs(self):
        return [self.raw_directory_to_ref(rootdir) for rootdir in self.get_raw_rootdirs()]

    def get_diritems_as_refs(self, directory_id):
        return [(self.raw_directory_to_ref(diritem) if diritem.get('isDir') else self.raw_song_to_ref(diritem)) for diritem in self.get_raw_dir(directory_id)]

    def get_diritems_as_tracks(self, directory_id):
        return [self.raw_song_to_track(diritem) for diritem in self.get_raw_dir(directory_id) if not diritem.get('isDir')]

    def get_artists_as_artists(self):
        return [self.raw_artist_to_artist(artist) for artist in self.get_raw_artists()]

    def get_playlists_as_refs(self):
        return [self.raw_playlist_to_ref(playlist) for playlist in self.get_raw_playlists()]

    def get_playlists_as_playlists(self):
        return [self.raw_playlist_to_playlist(playlist) for playlist in self.get_raw_playlists()]

    def get_playlist_as_playlist(self, playlist_id):
        return self.raw_playlist_to_playlist(self.get_raw_playlist(playlist_id))

    def get_playlist_as_songs_as_refs(self, playlist_id):
        playlist = self.get_raw_playlist(playlist_id)
        if playlist is None:
            return None
        return [self.raw_song_to_ref(song) for song in playlist.get('entry')]

    def get_artist_as_songs_as_tracks(self, artist_id):
        albums = self.get_raw_albums(artist_id)
        if albums is None:
            return None
        return [self.raw_song_to_track(song) for album in albums for song in self.get_raw_songs(album.get('id'))]

    def raw_song_to_ref(self, song):
        if song is None:
            return None
        return Ref.track(
            name=song.get('title') or UNKNOWN_SONG,
            uri=uri.get_song_uri(song.get('id')))

    def raw_song_to_track(self, song):
        if song is None:
            return None
        return Track(
            name=song.get('title') or UNKNOWN_SONG,
            uri=uri.get_song_uri(song.get('id')),
            bitrate=song.get('bitRate'),
            track_no=int(song.get('track')) if song.get('track') else None,
            date=str(song.get('year')) or 'none',
            genre=song.get('genre'),
            length=int(song.get('duration')) * 1000 if song.get('duration') else None,
            disc_no=int(song.get('discNumber')) if song.get('discNumber') else None,
            artists=[Artist(
                name=song.get('artist'),
                uri=uri.get_artist_uri(song.get('artistId')))],
            album=Album(
                name=song.get('album'),
                uri=uri.get_album_uri(song.get('albumId'))))

    def raw_album_to_ref(self, album):
        if album is None:
            return None
        return Ref.album(
            name=album.get('title') or album.get('name') or UNKNOWN_ALBUM,
            uri=uri.get_album_uri(album.get('id')))

    def raw_album_to_album(self, album):
        if album is None:
            return None
        return Album(
            name=album.get('title') or album.get('name') or UNKNOWN_ALBUM,
            uri=uri.get_album_uri(album.get('id')),
            artists=[Artist(
                name=album.get('artist'),
                uri=uri.get_artist_uri(album.get('artistId')))])

    def raw_directory_to_ref(self, directory):
        if directory is None:
            return None
        return Ref.directory(
            name=directory.get('title') or directory.get('name'),
            uri=uri.get_directory_uri(directory.get('id')))

    def raw_artist_to_ref(self, artist):
        if artist is None:
            return None
        return Ref.artist(
            name=artist.get('name') or UNKNOWN_ARTIST,
            uri=uri.get_artist_uri(artist.get('id')))

    def raw_artist_to_artist(self, artist):
        if artist is None:
            return None
        return Artist(
            name=artist.get('name') or UNKNOWN_ARTIST,
            uri=uri.get_artist_uri(artist.get('id')))

    def raw_playlist_to_playlist(self, playlist):
        if playlist is None:
            return None
        entries = playlist.get('entry')
        tracks = [self.raw_song_to_track(song) for song in entries] if entries is not None else None
        return Playlist(
            uri=uri.get_playlist_uri(playlist.get('id')),
            name=playlist.get('name'),
            tracks=tracks)

    def raw_playlist_to_ref(self, playlist):
        if playlist is None:
            return None
        return Ref.playlist(
            uri=uri.get_playlist_uri(playlist.get('id')),
            name=playlist.get('name'))

    def raw_imageuri_to_image(self, imageuri):
        return Image(
            uri=imageuri)

    def coverart_item_id_by_song_id(self, song_id):
        coverart_item_id = self.get_raw_song(song_id)
        if coverart_item_id is not None:
            return coverart_item_id.get('coverArt')
        else:
            return None

    def coverart_item_id_by_album_id(self, album_id):
        coverart_item_id = self.get_raw_album(album_id)
        if coverart_item_id is not None:
            return coverart_item_id.get('coverArt')
        else:
            return None

    def coverart_item_id_by_artist_id(self, artist_id):
        coverart_item_id = self.get_raw_artist(artist_id)
        if coverart_item_id is not None:
            return coverart_item_id.get('coverArt')
        else:
            return None

    def coverart_item_id_by_directory_id(self, directory_id):
        # FIXME: may take long when directory_id's parent dir has many subdirs
        dirinfo = self.get_raw_dirinfo(directory_id)
        if dirinfo is None:
            return None
        parentdir_id = dirinfo.get('parent')
        if parentdir_id is None:
            return None
        parentdiritems = self.get_raw_dir(parentdir_id)
        if parentdiritems is None:
            return None
        diritem = dict((d['id'], d) for d in parentdiritems).get(directory_id)
        return diritem.get('coverArt')
