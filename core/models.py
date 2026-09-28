from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
# Create your models here.

class Artist(models.Model): 
    spotify_id = models.CharField(max_length=30,primary_key = True)
    name = models.CharField(max_length=30)
    url = models.CharField(max_length=50, default="")
    
    genres = models.JSONField(blank=True, default=None, null=True)

class Song(models.Model):
    name = models.CharField(max_length = 25)
    genres = models.JSONField(default=list)
    artists = models.CharField(max_length=25, default="None")
    song_id = models.CharField(max_length=30, null=True)



class AppUser(models.Model):
    username = models.CharField(max_length=150, unique=True)
    password_hash=models.CharField(max_length=255)
    date_joined=models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

class SpotifyAccount(models.Model):
    user = models.OneToOneField(
        AppUser,
        on_delete = models.CASCADE,
        related_name="spotify_account",
    )
    access_token = models.CharField(max_length=255, null=True, blank=True)
    refresh_token = models.CharField(max_length=255, null=True, blank=True)
    token_expires_at = models.DateTimeField()
    baseline_updated_at = models.DateTimeField(default=timezone.now())

    profile_image_url = models.CharField(max_length=100,blank=True)
    spotify_id = models.CharField(max_length=255,unique=True)
    spotify_name = models.CharField(max_length=25, default="")
    top_tracks = models.JSONField(default=dict, blank=True)
    baseline_tracks = models.JSONField(default=dict, blank=True) 
    top_artists = models.JSONField(default=dict, blank=True) # key - artist, value - img url
    baseline_artists = models.JSONField(default=dict, blank=True)   
    top_genres = models.JSONField(default=dict, blank=True)

    connected_at = models.DateTimeField(auto_now_add=True)
    last_refreshed_at = models.DateTimeField(auto_now_add=True)

class Playlist(models.Model):
    spotify_user = models.ForeignKey(SpotifyAccount, on_delete=models.CASCADE, related_name="playlists")
    playlist_id = models.CharField(max_length=50, default="None")
    name = models.CharField(max_length = 25)
    songs = models.ManyToManyField(Song, related_name="songs")
    song_count = models.IntegerField(default=0)