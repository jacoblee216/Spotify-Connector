from .models import AppUser, SpotifyAccount, Playlist, Song
import requests
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
import math

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
def add_genres(spotify_account): # TO DO: Add genre field to artists to reduce API calls and improve testing efficiency
    decay_factor = 0.80
    calculated_genres = {}
    print("Working on calculating genres")
    for artist, attributes in spotify_account.top_artists.items():
        genres = get_genres_for_artist(artist)
        rank = attributes["index"]
        for genre in genres:
            if genre not in calculated_genres.keys():
                calculated_genres[genre] = math.pow(decay_factor, rank - 1)
            else:
                calculated_genres[genre] += math.pow(decay_factor, rank - 1)
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
            add_genres(spotify_account)
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
        for playlist in playlist_data["items"]:
            user_playlist, created = Playlist.objects.update_or_create(
                spotify_user=spotify_account,
                playlist_id=playlist["id"],
                defaults={
                    "name": playlist["name"],
                },
            )
            # print(playlist["name"]) # print for testing
            add_songs(playlist["id"], spotify_account)
    for object in Playlist.objects.all():
        if playlist_data["items"]:
            for playlist in playlist_data["items"]:
                if object.name == playlist["name"]:
                    break
            else:
                object.delete()
    else:
        print("No playlists found for this user.")
    return True
def add_songs(playlist_id, spotify_account): # function to add songs to playlist object 
    song_response= requests.get( # find way to tracks
        f"https://api.spotify.com/v1/playlists/{playlist_id}/items",
        headers={"Authorization": f"Bearer {spotify_account.access_token}"},
    )
    if song_response.status_code != 200:
        print("Song request failed.")
        print(song_response.text)
        return False
    song_data = song_response.json()
    
    songs = []
    song_count = 0
    for entry in song_data["items"]:
        track = entry.get("item")
        if entry["is_local"] == True:
            artist_names = "Local File Song"
            song_count += 1
            song_object, created = Song.objects.update_or_create(
                song_id=track["id"],
                defaults = {
                    "name": track["name"],
                    "artists": artist_names,
            }
            )
            songs.append(song_object)
            continue
        if not track:
            continue  # skip this entry, move to the next song
        else:
            artist_names = [artist["name"] for artist in track["artists"]]
        song_object, created = Song.objects.update_or_create(
            song_id=track["id"],
            defaults = {
                "name": track["name"],
                "artists": ", ".join(artist_names),
            }
        )
        song_count += 1
        songs.append(song_object)
    playlist = Playlist.objects.get(playlist_id=playlist_id,spotify_user=spotify_account)
    playlist.songs.add(*songs)
    playlist.song_count = song_count
    playlist.save()
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
        artist_names = []
        for artist in entry["artists"]:
            artist_names.append(artist["name"])
        attributes["artists"] = ", ".join(artist_names) # nested dict values: "artists", "index", "spots_moved"
        attributes["index"] = newCount
        newCount += 1
        tracks[entry["name"]] = attributes
    
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
    artists = {}
    newCount = 1
    for entry in top_artists["items"]:
        temp = 1000
        url = ""
        attributes = {}
        for image in entry["images"]:
            if image["height"] < temp:
                temp = image["height"]
                url = image["url"]
        artist_name = entry["name"]
        attributes["url"] = url
        attributes["index"] = newCount
        artists[artist_name] = attributes
        newCount += 1
    oldArtists = spotify_account.baseline_artists
    for key, value in artists.items():
        if key not in oldArtists.keys():
            value["spots_moved"] = 20 - value["index"]
        else:
            value["spots_moved"] = oldArtists[key]["index"] - value["index"]
    spotify_account.top_artists = artists
    spotify_account.save(update_fields=["top_artists"])
    return True
        
    
        
        
    
    


