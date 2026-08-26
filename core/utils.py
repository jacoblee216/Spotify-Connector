from .models import AppUser, SpotifyAccount, Playlist, Song
import requests
from django.conf import settings
from datetime import timedelta
from django.utils import timezone


def exchange_code_for_tokens(callback_code, user): # need to write another request for display_name and spotify_id
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
                "country": user_data.get("country",""),
                "profile_image_url": user_data["images"][0]["url"] if user_data.get("images") else "",

            },
        )
        if not exchange_code_for_playlist(spotify_account):
            return False
        if not add_top_tracks(spotify_account):
            return False
        if not add_top_artists(spotify_account):
            return False
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
        if not track:
            continue  # skip this entry, move to the next song
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
        f"https://api.spotify.com/v1/me/top/tracks",
        headers={"Authorization": f"Bearer {spotify_account.access_token}"},
    )
    if track_response.status_code != 200:
        print("Song request failed.")
        print(track_response.text)
        return False
    top_tracks = track_response.json()
    tracks = {}
    for entry in top_tracks["items"]:
        if entry["is_local"] == True:
            tracks[entry["name"]] = "Local File Song"
            continue
        artist_names = []
        for artist in entry["artists"]:
            artist_names.append(artist["name"])
        tracks[entry["name"]] = ", ".join(artist_names)
    spotify_account.top_tracks.update(tracks)
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
    print(top_artists)
    artists = {}
    for entry in top_artists["items"]:
        temp = 1000
        url = ""
        for image in entry["images"]:
            if image["height"] < temp:
                temp = image["height"]
                url = image["url"]
        artist_name = entry["name"]
        artists[artist_name] = url
    spotify_account.top_artists.update(artists)
    spotify_account.save(update_fields=["top_artists"])
    return True
        
    
        
        
    
    


