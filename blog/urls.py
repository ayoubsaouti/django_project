from django.urls import path
from .views import (
    PostListView,
    PostDetailView,
    PostCreateView,
    PostUpdateView,
    PostDeleteView,
    join_public_game,
    join_private_game,
    play_game,
    statistics,
)
from . import views

urlpatterns = [
    path('', PostListView.as_view(), name='blog-home'),
    path('post/<int:pk>/', PostDetailView.as_view(), name='post-detail'),
    path('post/new/', PostCreateView.as_view(), name='post-create'),
    path('post/<int:pk>/update/', PostUpdateView.as_view(), name='post-update'),
    path('post/<int:pk>/delete/', PostDeleteView.as_view(), name='post-delete'),
    path('game/<int:pk>/join/', join_public_game, name='join-public-game'),
    path('join-private-game/', join_private_game, name='join-private-game'),
    path('play/<int:post_id>/', play_game, name='play-game'),
    path('statistics/', statistics, name='statistics'),
    path('update-board/<int:post_id>/', views.update_board, name='update-board'),
    path('get-game-state/<int:post_id>/', views.get_game_state, name='get_game_state'),
    path('surrender_game/<int:post_id>/', views.surrender_game, name='surrender_game'),
    path('join_tournament/', views.join_tournament, name='join_tournament'),
    path('tournament/<int:tournament_id>/', views.tournament_detail, name='tournament_detail'),
    path('play_tournament/<int:tournament_id>/', views.play_tournament, name='play_tournament'),
    path('update_game_board/<int:post_id>/', views.update_game_board, name='update_game_board'),
    path('get_game_state_tournament/<int:post_id>/', views.get_game_state_tournament, name='get_game_state_tournament'),

]
