from urlparse import urlparse
from urllib import urlencode
import libsonic
import logging
import itertools
import requests
import urllib
from mopidy.models import Track, Album, Artist, Playlist, Ref, SearchResult, Image
import mopidy_subidy
import re
from mopidy_subidy import uri

logger = logging.getLogger(__name__)

RESPONSE_OK = u'ok'
UNKNOWN_SONG = u'Unknown Song'
UNKNOWN_ALBUM = u'Unknown Album'
UNKNOWN_ARTIST = u'Unknown Artist'
MAX_SEARCH_RESULTS = 100
MAX_LIST_RESULTS = 500

ref_sort_key = lambda ref: ref.name

def string_nums_nocase_sort_key(s):
    segments = []
    for substr in re.split(r'(\d+)', s):
        if substr.isdigit():
            seg = int(substr)
        else:
            seg = substr.lower()
        segments.append(seg)
    return segments

def diritem_sort_key(item):
    isdir = item['isDir']
    if isdir:
        key = string_nums_nocase_sort_key(item['title'])
    else:
        key = int(item.get('track', 1))
    return (isdir, key)

def get_subsonic_api_with_config(config):
    subidy_config = config['subidy']
    sapi = SubsonicApi(
        url=subidy_config['url'],
        username=subidy_config['username'],
        password=subidy_config['password'],
        legacy_auth=subidy_config['legacy_auth'])
    sapi.mopidy_base_uri = subidy_config['uri_prefix']
    return sapi

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

    def get_subsonic_uri(self, view_name, params, censor=False):
        di_params = {}
        di_params.update(params)
        di_params.update(c='mopidy')
        di_params.update(v=self.connection.apiVersion)
        if censor:
            di_params.update(u='*****', p='*****')
        else:
            di_params.update(u=self.username, p=self.password)
        return '{}/{}.view?{}'.format(self.url, view_name, urlencode(di_params))

    def get_song_stream_uri(self, song_id):
        return self.get_subsonic_uri('stream', dict(id=song_id))

    def get_censored_song_stream_uri(self, song_id):
        return self.get_subsonic_uri('stream', dict(id=song_id), True)

    def get_coverart_image_uri(self, aid):
        return self.get_subsonic_uri('getCoverArt', dict(id=aid))

    def get_censored_coverart_image_uri(self, aid):
        return self.get_subsonic_uri('getCoverArt', dict(id=aid), True)

    def find_raw(self, query, exclude_artists=False, exclude_albums=False, exclude_songs=False):
        try:
            response = self.connection.search2(
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

    def get_raw_artists(self):
        try:
            response = self.connection.getArtists()
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of artists.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        letters = response.get('artists').get('index')
        if letters is not None:
            artists = [artist for letter in letters for artist in letter.get('artist') or []]
            return artists
        logger.warning('Subsonic does not seem to have any artists in it\'s library.')
        return []

    def get_raw_rootdirs(self):
        try:
            response = self.connection.getIndexes()
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading list of rootdirs.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        letters = response.get('indexes').get('index')
        if letters is not None:
            artists = [artist for letter in letters for artist in letter.get('artist') or []]
            return artists
        logger.warning('Subsonic does not seem to have any rootdirs in its library.')
        return []

    def get_song_by_id(self, song_id):
        song = self.get_raw_song(song_id)
        return self.raw_song_to_track(song) if song is not None else None

    def get_album_by_id(self, album_id):
        album = self.get_raw_album(album_id)
        return self.raw_album_to_album(album) if album is not None else None

    def get_artist_by_id(self, artist_id):
        artist = self.get_raw_artist(artist_id)
        return self.raw_artist_to_artist(artist) if artist is not None else None

    def get_coverart_image_by_id(self, a_id):
        return self.raw_imageuri_to_image(''.join((self.mopidy_base_uri, ('' if self.mopidy_base_uri.endswith("/") else '/'), mopidy_subidy.SubidyExtension.ext_name, '/cover_art?id=', urllib.quote_plus(a_id))))

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
            diritems = directory.get('child')
            return sorted(diritems, key=diritem_sort_key)
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
            return sorted(albums, key=lambda album: string_nums_nocase_sort_key(album['name']))
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

    def get_raw_album_list(self, ltype, size=MAX_LIST_RESULTS):
        try:
            response = self.connection.getAlbumList2(ltype=ltype, size=size)
        except Exception as e:
            logger.warning('Connecting to subsonic failed when loading album list.')
            return []
        if response.get('status') != RESPONSE_OK:
            logger.warning('Got non-okay status code from subsonic: %s' % response.get('status'))
            return []
        albums = response.get('albumList2').get('album')
        if albums is not None:
            return albums
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

    def get_albums_as_refs(self, artist_id=None):
        albums = (self.get_raw_album_list('alphabeticalByName') if artist_id is None else self.get_raw_albums(artist_id))
        return [self.raw_album_to_ref(album) for album in albums]

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
