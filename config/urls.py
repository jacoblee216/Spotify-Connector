"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", views.home, name="home"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.login_view, name="logout"),
    path('register/', views.register, name="register"),
    path('spotify/login', views.spotify_login, name="spotify_login"),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),
    path('refresh/playlists', views.refresh_playlists, name='refresh_playlists'),
    path('refresh_top_tracks/', views.refresh_top_tracks, name='refresh_top_tracks'),
    path('refresh_top_artists/', views.refresh_top_artists, name='refresh_top_artists'),
]
