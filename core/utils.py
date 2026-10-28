from .models import AppUser, SpotifyAccount, Playlist, Song, Artist
import requests
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
import math
import time

import requests
import time
def get_genres_for_artist(artist_name): # have to work on checking these requests
    mbid = get_artist_mbid(artist_name)
    if not mbid:
        return []
    time.sleep(1)  # respect rate limit between the two calls
    genres = get_artist_genres(mbid)
    return genres
def get_artist_mbid(artist_name):
    response = requests.get(
        "https://musicbrainz.org/ws/2/artist",
        params={"query": artist_name, "fmt": "json", "limit": 1},
        headers={"User-Agent": "Spotify Dashboard App/0.1 (jacoblee242006@gmail.com)"},
    )
    if response.status_code != 200:
        return None
    data = response.json()
    artists = data.get("artists", [])
    if not artists:
        return None
    return artists[0]["id"]  # this is the MBID
def get_artist_genres(mbid):
    response = requests.get(
        f"https://musicbrainz.org/ws/2/artist/{mbid}",
        params={"inc": "genres", "fmt": "json"},
        headers={"User-Agent": "Spotify Dashboard App/0.1 (jacoblee242006@gmail.com)"},
    )
    if response.status_code != 200:
        return []
    data = response.json()
    return [g["name"] for g in data.get("genres", [])]
def calculate_top_genres(spotify_account):
    start = time.perf_counter()
    decay_factor = 0.80
    calculated_genres = {}
    for artist, attributes in spotify_account.top_artists.items(): # key = spotify artist id
        genres = Artist.objects.get(spotify_id = artist).genres # calculating genres based off top artists
        if genres == None:
            print(f"{attributes["name"]} is missing genre field")
            continue
        rank = attributes["index"]
        for genre in genres:
            if genre not in calculated_genres:
                calculated_genres[genre] = math.pow(decay_factor, rank - 1)
            else:
                calculated_genres[genre] += math.pow(decay_factor, rank - 1)
    for song_name, attributes in spotify_account.top_tracks.items(): # calculating genres based off top songs
        for artist in attributes["artists"]:
            artist_id = artist["id"]
            artist_name = artist["name"]
            try:
                genres = Artist.objects.get(spotify_id = artist_id).genres
            except Artist.DoesNotExist:
                print(f"{song_name}: artist {artist_name} is not in the Artist table")
                continue
            if genres == None:
                print(f"{artist_name} is missing genre field")
                continue
            rank = attributes["index"]
            for genre in genres:
                if genre not in calculated_genres:
                    calculated_genres[genre] = math.pow(decay_factor, rank - 1)
                else:
                    calculated_genres[genre] += math.pow(decay_factor, rank - 1)
    end = time.perf_counter()
    print(f"Took {end - start:.4f} seconds")
    sorted_genres = {}
    temp_weight = 0
    while calculated_genres:
        temp_weight = 0
        temp_genre = ""
        for genre, weight in calculated_genres.items():
            if weight > temp_weight:
                temp_weight = weight
                temp_genre = genre
        sorted_genres[temp_genre] = temp_weight
        calculated_genres.pop(temp_genre)
    spotify_account.top_genres = sorted_genres
    spotify_account.save()
    return True
def fetch_genres_from_ids(artists_needing_genres):
    for artist in artists_needing_genres:
        artist.genres = get_genres_for_artist(artist.name)
        artist.save(update_fields=["genres"])
        time.sleep(1)
        print(f"{artist.name} was missing genres")
    
def exchange_code_for_tokens(callback_code, user): 
    print(f"Token exchange attempt with code: {callback_code[:15]}...")
    response = requests.post(
    "https://accounts.spotify.com/api/token",   # URL — this is Spotify's fixed endpoint for token exchange
    data={                                        # the BODY of the request — form fields Spotify expects
        "grant_type": "authorization_code",
        "code": callback_code,
        "redirect_uri": settings.REDIRECT_URI,
        "client_id": settings.CLIENT_ID,
        "client_secret": settings.CLIENT_SECRET,
    },
)
    print("Token exchange status:", response.status_code)
    if response.status_code != 200:
        print("General request failed")
        print(response.text)
        return False
    else:
        token_data = response.json()

        user_response = requests.get( 
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
        if user_response.status_code != 200:
            print("User request failed")
            print(user_response.text)
            return False
        
        user_data = user_response.json()
        spotify_account, created = SpotifyAccount.objects.update_or_create(
            user=user,  # lookup field — find the existing row for this user (or create one)
            defaults={   # fields to set/update on that row
                "access_token": token_data["access_token"],
                "refresh_token": token_data["refresh_token"],
                "token_expires_at": timezone.now() + timedelta(seconds=token_data["expires_in"]),
                "spotify_id": user_data["id"],
                "spotify_name": user_data.get("display_name", ""),
                "profile_image_url": user_data["images"][0]["url"] if user_data.get("images") else "",

            },
        )
        """
        Can't have one function be the gateway to all these API calls
        Need to split up these functions and have them each have a gate to be called from
        """
        
        if not exchange_code_for_playlist(spotify_account): 
            return False
        if not add_top_tracks(spotify_account):
            return False
        if not add_top_artists(spotify_account):
            return False
        if spotify_account.top_genres == None:
            return False
        else:
            calculate_top_genres(spotify_account)
        return True
def exchange_code_for_playlist(spotify_account): 
    playlist_response = requests.get(
        "https://api.spotify.com/v1/me/playlists",
        headers={"Authorization": f"Bearer {spotify_account.access_token}"},
    )
    if playlist_response.status_code != 200:
        print("Playlist request failed.")
        print(playlist_response.text)
        return False
    playlist_data = playlist_response.json()
    # print("Total playlists:", playlist_data["total"]) # print for testing
    if playlist_data["items"]:
        song_count = 0
        for playlist in playlist_data["items"]:
            user_playlist, created = Playlist.objects.update_or_create(
                spotify_user=spotify_account,
                playlist_id=playlist["id"],
                defaults={
                    "name": playlist["name"],
                },
            )
            print(playlist["name"])
            song_count = add_songs(playlist["id"], spotify_account)
        print(f"{playlist["name"]} - Total: {song_count}")
    else:
        print("No playlists found for this user.")
    for object in spotify_account.playlists.all():
        if playlist_data["items"]:
            for playlist in playlist_data["items"]:
                if object.name == playlist["name"]:
                    break
            else:
                object.delete()
    return True
def add_songs(playlist_id, spotify_account):
    headers = {"Authorization": f"Bearer {spotify_account.access_token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/items"
    params = {"limit": 50}

    songs = []
    song_count = 0

    while url:
        song_response = requests.get(url, headers=headers, params=params)
        if song_response.status_code != 200:
            print("Song request failed.")
            print(song_response.text)
            return False
        song_data = song_response.json()

        for entry in song_data["items"]:
            track = entry.get("item")
            if not track:
                continue  # check this first, before using track

            if entry.get("is_local"):
                song_id = track.get("id") or track.get("uri")  # local files have no id
                artist_names = "Local File Song"
            else:
                song_id = track["id"]
                artist_names = ", ".join(a["name"] for a in track.get("artists", []))

            if not song_id:
                continue

            song_object, created = Song.objects.update_or_create(
                song_id=song_id,
                defaults={"name": track["name"], "artists": artist_names},
            )
            songs.append(song_object)
            song_count += 1

        url = song_data.get("next")  # next page URL, or None on the last page
        params = None                # the next URL already includes limit/offset

    playlist = Playlist.objects.get(playlist_id=playlist_id, spotify_user=spotify_account)
    playlist.songs.set(songs)        # replaces the old set so removed songs disappear
    playlist.song_count = song_count
    playlist.save()
    return song_count
def add_top_tracks(spotify_account):
    track_response= requests.get( 
        f"https://api.spotify.com/v1/me/top/tracks?limit=50",
        headers={"Authorization": f"Bearer {spotify_account.access_token}"},
    )
    if track_response.status_code != 200:
        print("Song request failed.")
        print(track_response.text)
        return False
    top_tracks = track_response.json()
    tracks = {} # new tracks to be added
    newCount = 1
    for entry in top_tracks["items"]:
        attributes = {}
        if entry["is_local"] == True:
            attributes["artists"] = "Local File Song"
            attributes["index"] = newCount
            newCount += 1
            tracks[entry["name"]] = attributes
            continue
        artists = []
        existing_artist_ids = []
        for artist in entry["artists"]:
            artist_data = {}
            artist_data["id"] = artist["id"]
            existing_artist_ids.append(artist["id"])
            artist_data["name"] = artist["name"]
            artists.append(artist_data)
        attributes["artists"] = artists
        attributes["index"] = newCount
        newCount += 1
        tracks[entry["name"]] = attributes
    artist_names = {
        a["id"]: a["name"]
        for track in tracks.values()              # tracks = your dict keyed by song name
        if isinstance(track["artists"], list)     # skip local files
        for a in track["artists"]
    }

    existing_ids = set(
        Artist.objects.filter(spotify_id__in=artist_names.keys())
        .values_list("spotify_id", flat=True)
    )

    missing_ids = set(artist_names) - existing_ids
    
    Artist.objects.bulk_create(
        [Artist(spotify_id=aid, name=artist_names[aid]) for aid in missing_ids],
        ignore_conflicts=True
    )
    artists_needing_genres = list( # find the artists needing genres in the global model
        Artist.objects.filter(
            spotify_id__in = artist_names.keys(),
            genres__isnull = True,
        )
    )
    if artists_needing_genres:
        fetch_genres_from_ids(artists_needing_genres)
        
    oldTracks = spotify_account.baseline_tracks
    for key, value in tracks.items(): # iterate through new tracks first
        if key not in oldTracks.keys(): # check if new track is in old track, if not assign spots moved to (size of list - new track's current position)
            value["spots_moved"] = 50 - value["index"]
        else: # case: track moved position in list, so spots_moved is old position - new position in list (e.g old position: 14 - new position: 11 = +3)
            value["spots_moved"] = oldTracks[key]["index"] - value["index"]
    spotify_account.top_tracks = tracks
    spotify_account.save(update_fields=["top_tracks"])
    return True
def add_top_artists(spotify_account):
    artist_response= requests.get( 
        f"https://api.spotify.com/v1/me/top/artists",
        headers={"Authorization": f"Bearer {spotify_account.access_token}"},
    )
    if artist_response.status_code != 200:
        print("Song request failed.")
        print(artist_response.text)
        return False
    top_artists = artist_response.json()
    
    newCount = 1
    artists = {} # key - id, values - name = artist name and genres = None
    for entry in top_artists["items"]: # create dictionary for all returned top artists
        artist_data = {}
        url = ""
        temp = 1000
        for image in entry["images"]:
            if image["height"] < temp:
                temp = image["height"]
                url = image["url"]
        artist_data["url"] = url
        artist_data["name"] = entry["name"]
        artist_data["index"] = newCount
        artists[entry["id"]] = artist_data
        newCount += 1
        
    existing_ids = set( # find all existing artists in the global Artist model
        Artist.objects.filter(spotify_id__in=artists.keys())
        .values_list("spotify_id", flat=True)
    )
    missing_ids = set(artists) - existing_ids # find missing artists not in the global model
    Artist.objects.bulk_create(
        [Artist(spotify_id=aid, name=artists[aid]["name"]) for aid in missing_ids],
        ignore_conflicts=True
    )
    
    artists_needing_genres = list( # find the artists needing genres in the global model
        Artist.objects.filter(
            spotify_id__in = artists.keys(),
            genres__isnull = True,
        )
    )
    if artists_needing_genres:
        fetch_genres_from_ids(artists_needing_genres)
        
    oldArtists = spotify_account.baseline_artists
    for key, value in artists.items():
        if key not in oldArtists.keys(): # case: wasn't in previous list of top artists (spots moved from the end of the list)
            value["spots_moved"] = 20 - value["index"]
        else: # case: was in previous list of top artists (spots moved from previous spot)
            value["spots_moved"] = oldArtists[key]["index"] - value["index"]
    spotify_account.top_artists = artists
    spotify_account.save(update_fields=["top_artists"])

    return True
        
    
        
        
    
    


