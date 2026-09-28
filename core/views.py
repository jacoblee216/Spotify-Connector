from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Song, Playlist, AppUser, SpotifyAccount
from urllib.parse import urlencode
from django.conf import settings
from django.utils import timezone
from .utils import *
from datetime import timedelta
from django.contrib import messages
from django.contrib.messages import get_messages
from functools import wraps
"""

GOAL OF PROJECT:
Create an app that allows users see playlists, other user's songs, and favorite genres
Implement rate limiting
Hand out access tokens after authentication to control rates



Potential features and additions:
- Page to determine user's music taste

TO DO:
Calculate top genres through top tracks as well (already done with top artists)
Refactor top artist model function to create the check if object exists 
"""
def login_required_app_user(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = request.session.get("app_user_id")
        if not user_id:
            return redirect("login") # case: user does not exist
        
        try:
            request.app_user = AppUser.objects.get(id=user_id) # add app user to the request
        except AppUser.DoesNotExist:
            request.session.pop("app_user_id", None)  # clean up stale session
            return redirect("login")
        
        return view_func(request, *args, **kwargs)
    return wrapper
@login_required_app_user
def home(request):
    user = request.app_user
    if request.method == "POST":
        action = request.POST.get("action") 
        if action == "disconnect": # handles logout button post request
            spotify_account = SpotifyAccount.objects.filter(user=user).first()
            if spotify_account:
                spotify_account.access_token = None
                spotify_account.refresh_token = None
                spotify_account.save()
            return redirect("home")
    spotify_profile = SpotifyAccount.objects.filter(user=user).first()
    is_connected = spotify_profile and spotify_profile.access_token is not None
    playlists = Playlist.objects.none()
    top_tracks = {}
    top_artists = []
    genres = []
    if is_connected:         
        playlists = spotify_profile.playlists.all().order_by('-song_count')
        top_tracks = spotify_profile.top_tracks
        top_artists = spotify_profile.top_artists
        genres = spotify_profile.top_genres
        genres = list(genres)[:5]
    context = {
        "user": user,
        "spotify_profile": spotify_profile if is_connected else None,
        "top_artists": top_artists,
        "playlists": playlists,
        "top_tracks": top_tracks,
        "genres": genres,
    }
    return render(request, "home.html", context)
def login_view(request): # also implement a way to get rid of logged in tokens when clicking log out
    if request.method == "POST":
        print(request.POST)
        print(request.method)
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = AppUser.objects.filter(username=username).first()
        if not username or not password: 
            return render(request, "login.html")
        if not user: # case: username not found
            error = f"User not found with username \"{username}\""
            return render(request, "login.html", {"error": error})
        
        if not user.check_password(password): # case: password is incorrect for that user
            error = f"Incorrect password for \"{username}\""
            return render(request, "login.html", {"error": error})
        
        request.session["app_user_id"] = user.id
        return redirect("home")
    return render(request, "login.html")
def logout_view(request):
    request.session.pop("app_user_id", None)
    return redirect("login")
def register(request):
    print("METHOD: ", request.method)
    if request.method == "POST":
        username = request.POST.get("username")
        first_password = request.POST.get("password1")  # password1 is first password, password2 is confirm password
        confirmed_password = request.POST.get("password2")
        if not username or not first_password or not confirmed_password: # case: empty text field
            return render(request, "register.html", {"error": "Error: Empty Field"})
        
        if AppUser.objects.filter(username=username).exists(): # case: username is taken
            return render(request, "register.html", {"error": f"Username \"{username}\" is already taken"})
        
        if (first_password != confirmed_password): # case: passwords do not match
            return render(request, "register.html", {"error": "Passwords do not match"}) 
        
        user = AppUser(username=username)
        user.set_password(first_password)
        user.save()
        request.session["app_user_id"] = user.id
        return redirect("home")

    return render(request, "register.html")
def spotify_callback(request):
    callback_code = request.GET.get("code")
    if not callback_code:
        messages.error(request, "Spotify authorization failed. Please try again.")
        return redirect("home") # FUTURE: need error message to pop up 

    user = AppUser.objects.get(id=request.session["app_user_id"])
    if not exchange_code_for_tokens(callback_code, user):
        messages.error(request, "Couldn't connect your spotify account. Please try again.")
        return redirect("home")  # exchange failed
    
    messages.success(request, "Spotify account connected successfully.")
    return redirect("home")
def spotify_login(request):
    client_id = settings.CLIENT_ID
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "http://127.0.0.1:8000/spotify/callback/",
        "scope": ("user-read-playback-state "
        "playlist-read-private "
        "user-top-read "
        "user-read-recently-played "
        "user-read-private"),
        "show_dialog": "true",
    }

    spotify_auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urlencode(params)
    )

    return redirect(spotify_auth_url)
@login_required_app_user
def refresh_playlists(request):
    spotify_profile = SpotifyAccount.objects.filter(user=request.app_user).first()
    if (spotify_profile):
        if exchange_code_for_playlist(spotify_profile):
            messages.success(request, "Playlists refreshed successfully!")
            return redirect("home")
        messages.error(request, "Couldn't refresh playlists")
        return redirect("home")
    else:
        messages.error(request, "No user found")
        return redirect("home")
@login_required_app_user
def refresh_top_tracks(request):
    spotify_profile = SpotifyAccount.objects.filter(user=request.app_user).first()
    if (spotify_profile):
        if add_top_tracks(spotify_profile):
            if timezone.now() - spotify_profile.baseline_updated_at > timedelta(seconds=15):
                print("Cooldown passed")
                spotify_profile.baseline_tracks = spotify_profile.top_tracks
                spotify_profile.baseline_updated_at = timezone.now()
                spotify_profile.save()
            messages.success(request, "Tracks refreshed successfully!")
            return redirect("home")
        messages.error(request, "Couldn't refresh tracks")
        return redirect("home")
    else:
        messages.error(request, "No user found")
        return redirect("home")
@login_required_app_user
def refresh_top_artists(request):
    spotify_profile = SpotifyAccount.objects.filter(user=request.app_user).first()
    if (spotify_profile):
        if add_top_artists(spotify_profile):
            if timezone.now() - spotify_profile.baseline_updated_at > timedelta(seconds=15):
                print("Cooldown passed")
                spotify_profile.baseline_artists = spotify_profile.top_artists
                spotify_profile.baseline_updated_at = timezone.now()
                spotify_profile.save()
            messages.success(request, "Artists refreshed successfully!")
            return redirect("home")
        messages.error(request, "Couldn't refresh artists")
        return redirect("home")
    else:
        messages.error(request, "No user found")
        return redirect("home")
@login_required_app_user
def refresh_genres(request):
    spotify_profile = SpotifyAccount.objects.filter(user=request.app_user).first()
    if (spotify_profile):
        if calculate_top_genres(spotify_profile):
            if timezone.now() - spotify_profile.baseline_updated_at > timedelta(seconds=15):
                print("Cooldown passed")
                spotify_profile.save()
            messages.success(request, "Genres refreshed successfully!")
            return redirect("home")
        messages.error(request, "Couldn't refresh genres")
        return redirect("home")
    else:
        messages.error(request, "No user found")
        return redirect("home")