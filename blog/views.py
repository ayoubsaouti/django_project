import json
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from users.models import Profile
from django.db.models import Q, Count
from django.db.models.functions import TruncDay
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView
)
from .models import Post, Tournament


def home(request):
    context = {
        'posts': Post.objects.filter(type=Post.PUBLIC, gameOver=False)  # Only public and not finished posts
    }
    return render(request, 'blog/home.html', context)

class PostListView(ListView):
    model = Post
    template_name = 'blog/home.html'  # <app>/<model>_<viewtype>.html
    context_object_name = 'posts'
    ordering = ['-date_posted']

    def get_queryset(self):
        # Exclure les jeux de tournoi et les jeux terminés
        return Post.objects.filter(tournament__isnull=True, type=Post.PUBLIC, gameOver=False).order_by('-date_posted')



class PostDetailView(DetailView):
    model = Post


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    fields = ['title', 'size', 'alignmentToWin', 'type', 'max_moves']

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.surrender = False  # Initialiser le champ surrender à False
        response = super().form_valid(form)
        if form.instance.type == 'PRIVATE':
            messages.success(self.request, f"ACCESS CODE : {form.instance.access_code}")
        return response

class PostUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    fields = ['title', 'size', 'alignmentToWin', 'type', 'max_moves']

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        if form.instance.type == 'PRIVATE':
            messages.success(self.request, f"ACCESS CODE : {form.instance.access_code}")
        return response

    def test_func(self):
        post = self.get_object()
        if self.request.user == post.author:
            return True
        return False


class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    success_url = '/'

    def test_func(self):
        post = self.get_object()
        if self.request.user == post.author:
            return True
        return False

@login_required
def join_public_game(request, pk):
    game = get_object_or_404(Post, pk=pk)

    if request.method == 'POST':
        if not game.player2 and request.user != game.author:
            game.player2 = request.user
            game.save()
            return redirect(game.get_absolute_url())

    return render(request, 'blog/post_detail.html', {'object': game})

@login_required
def join_private_game(request):
    error = None

    if request.method == 'POST':
        access_code = request.POST.get('access_code')
        game = get_object_or_404(Post, access_code=access_code)

        if game.type == Post.PRIVATE and not game.player2:
            game.player2 = request.user
            game.save()
            return redirect(game.get_absolute_url())
        else:
            error = "Cette partie est déjà remplie."

    return render(request, 'blog/join_private_game.html', {'error': error})  # Assurez-vous que le chemin est correct


@login_required
def play_game(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    # Initialiser current_player si c'est une nouvelle partie
    if not post.current_player:
        if post.player2:  # Assurez-vous qu'il y a un deuxième joueur
            post.current_player = post.author.username  # Le joueur 1 commence
            post.save()
        else:
            # Vous pourriez vouloir retourner une page d'attente ou une erreur si le jeu ne peut pas commencer
            return render(request, 'blog/play_game.html', {'post': post, 'error': 'En attente d\'un deuxième joueur.'})

    # Passer les données nécessaires au template
    context = {
        'post': post,
        'board': post.board,
        'current_player': post.current_player,  # Ajouter current_player au contexte
        'player1': post.author.username,
        'player2': post.player2.username if post.player2 else None,
        'player1_symbol': post.author.profile.symbol.url,
        'player2_symbol': post.player2.profile.symbol.url if post.player2 else None,
    }

    return render(request, 'blog/play_game.html', context)

@csrf_exempt
def update_board(request, post_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            board = data.get('board')
            user = request.user.username

            # Ajout de logs pour vérifier les données reçues
            print(f"Received board: {board}")
            print(f"User: {user}")

            # Récupérer le jeu en cours
            game = Post.objects.get(id=post_id)

            # Vérifiez si le joueur actuel est le joueur dont c'est le tour
            if game.current_player != user:
                return JsonResponse({'status': 'error', 'message': 'Ce n\'est pas votre tour'}, status=400)

            # Vérifiez que le tableau est bien formé
            if not board or not isinstance(board, list) or not all(isinstance(row, list) for row in board):
                return JsonResponse({'status': 'error', 'message': 'Tableau de jeu invalide'}, status=400)

            # Mettez à jour le tableau dans la base de données
            game.board = board

            symbol = 'X' if game.current_player == game.author.username else 'O'
            alignment_to_win = game.alignmentToWin

            # Vérifier les conditions de victoire
            if check_victory(board, symbol, alignment_to_win):
                game.winner_player = game.author if symbol == 'X' else game.player2
                game.loser_player = game.player2 if symbol == 'X' else game.author
                game.gameOver = True

                # Mettre à jour les scores des utilisateurs
                if symbol == 'X':
                    winner_profile = game.author.profile
                    loser_profile = game.player2.profile
                else:
                    winner_profile = game.player2.profile
                    loser_profile = game.author.profile

                # Incrémenter le score du gagnant
                winner_profile.update_score(game.size, alignment_to_win)

                # Gestion de la configuration pour le perdant
                config_key = f'G{game.size}A{alignment_to_win}'
                if config_key not in loser_profile.scores:
                    loser_profile.scores[config_key] = 0

                loser_profile.save()
                game.save()

                return JsonResponse({
                    'status': 'success',
                    'winner': game.winner_player.username,
                    'loser': game.loser_player.username
                }, status=200)

            # Changez le joueur actuel
            if game.current_player == game.author.username:
                game.current_player = game.player2.username
            else:
                game.current_player = game.author.username

            game.save()

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            # Ajout de logs pour vérifier l'exception
            print(f"Exception: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def get_game_state(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    board = post.board
    current_player = post.current_player
    return JsonResponse({
        'board': board,
        'current_player': current_player,
        'surrender': post.surrender,
        'winner': post.winner_player.username if post.winner_player else None,
        'loser': post.loser_player.username if post.loser_player else None,
        'gameOver': post.gameOver,
        'draw': post.draw
    })

@csrf_exempt
def update_board(request, post_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            board = data.get('board')
            user = request.user.username

            # Récupérer le jeu en cours
            game = Post.objects.get(id=post_id)

            # Vérifiez si le joueur actuel est le joueur dont c'est le tour
            if game.current_player != user:
                return JsonResponse({'status': 'error', 'message': 'Ce n\'est pas votre tour'}, status=400)

            # Vérifiez que le tableau est bien formé
            if not board or not isinstance(board, list) or not all(isinstance(row, list) for row in board):
                return JsonResponse({'status': 'error', 'message': 'Tableau de jeu invalide'}, status=400)

            size = len(board)
            if any(len(row) != size for row in board):
                return JsonResponse({'status': 'error', 'message': 'Tableau de jeu mal formé'}, status=400)

            # Mettez à jour le tableau dans la base de données
            game.board = board

            symbol = 'X' if game.current_player == game.author.username else 'O'
            alignment_to_win = game.alignmentToWin

            # Vérifier les conditions de victoire
            if check_victory(board, symbol, alignment_to_win):
                game.winner_player = game.author if symbol == 'X' else game.player2
                game.loser_player = game.player2 if symbol == 'X' else game.author
                game.gameOver = True

                # Mettre à jour les scores des utilisateurs
                winner_profile = Profile.objects.get(user=game.winner_player)
                winner_profile.update_score(game.size, alignment_to_win)

                game.save()
                return JsonResponse({'status': 'success', 'winner': game.winner_player.username, 'loser': game.loser_player.username}, status=200)

            # Incrémentez le nombre de coups joués
            game.moves_played += 1

            # Vérifiez si le nombre maximum de coups a été atteint
            if game.moves_played >= game.max_moves:
                game.draw = True
                game.gameOver = True
                game.save()
                return JsonResponse({'status': 'success', 'draw': True}, status=200)


            # Changez le joueur actuel
            if game.current_player == game.author.username:
                game.current_player = game.player2.username
            else:
                game.current_player = game.author.username

            game.save()

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            # Ajout de logs pour vérifier l'exception
            print(f"Exception: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)



@csrf_exempt
def surrender_game(request, post_id):
    if request.method == 'POST':
        try:
            game = Post.objects.get(id=post_id)
            game.surrender = True
            game.gameOver = True  # Mettre fin à la partie

            game.current_user = request.user
            # Détermine le joueur qui abandonne et le joueur qui gagne
            if game.current_player == game.author.username:
                game.loser_player = game.author
                game.winner_player = game.player2
            else:
                game.loser_player = game.player2
                game.winner_player = game.author

            # Mettre à jour les scores des utilisateurs
            winner_profile = Profile.objects.get(user=game.winner_player)
            winner_profile.update_score(game.size, game.alignmentToWin)

            game.save()

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def check_victory(board, symbol, alignment_to_win):
    size = len(board)

    def check_line(line):
        count = 0
        for cell in line:
            if cell == symbol:
                count += 1
                if count == alignment_to_win:
                    return True
            else:
                count = 0
        return False

    # Check rows
    for i, row in enumerate(board):
        print(f"Checking row {i}: {row}")
        if check_line(row):
            return True

    # Check columns
    for col in range(size):
        column = [board[row][col] for row in range(size)]
        print(f"Checking column {col}: {column}")
        if check_line(column):
            return True

    # Check diagonals
    def check_diagonals(row, col, symbol):
        # Diagonale principale
        count_principal = 0
        for i in range(-alignment_to_win + 1, alignment_to_win):
            r, c = row + i, col + i
            if 0 <= r < size and 0 <= c < size and board[r][c] == symbol:
                count_principal += 1
                if count_principal == alignment_to_win:
                    return True
            else:
                count_principal = 0

        # Diagonale inverse
        count_inverse = 0
        for i in range(-alignment_to_win + 1, alignment_to_win):
            r, c = row - i, col + i
            if 0 <= r < size and 0 <= c < size and board[r][c] == symbol:
                count_inverse += 1
                if count_inverse == alignment_to_win:
                    return True
            else:
                count_inverse = 0

        return False

    # Check all diagonals
    for row in range(size):
        for col in range(size):
            if check_diagonals(row, col, symbol):
                return True

    return False

@login_required
def statistics(request):
    user = request.user

    # Récupérer les statistiques des parties normales jouées par jour
    normal_games_data = Post.objects.filter(
        Q(author=user) | Q(player2=user)
    ).filter(tournament__isnull=True).annotate(day=TruncDay('date_posted')).values('day').annotate(total_games=Count('id')).order_by('day')

    # Récupérer les statistiques des parties de tournoi jouées par jour
    tournament_games_data = Post.objects.filter(
        Q(author=user) | Q(player2=user) | Q(player3=user) | Q(player4=user)
    ).filter(tournament__isnull=False).annotate(day=TruncDay('date_posted')).values('day').annotate(total_games=Count('id')).order_by('day')

    # Fusionner les jours pour avoir tous les jours joués (soit normal, soit tournoi)
    all_days = sorted(set(entry['day'] for entry in normal_games_data).union(entry['day'] for entry in tournament_games_data))
    days = [day.strftime('%Y-%m-%d') for day in all_days]

    # Initialiser les listes de comptage
    normal_games_played = [0] * len(days)
    tournament_games_played = [0] * len(days)

    # Remplir les listes de comptage avec les données
    for entry in normal_games_data:
        day_index = days.index(entry['day'].strftime('%Y-%m-%d'))
        normal_games_played[day_index] = entry['total_games']

    for entry in tournament_games_data:
        day_index = days.index(entry['day'].strftime('%Y-%m-%d'))
        tournament_games_played[day_index] = entry['total_games']

    # Récupérer les configurations disponibles pour l'utilisateur
    profile = Profile.objects.get(user=user)
    user_scores = json.loads(profile.scores)
    configurations = list(user_scores.keys())

    # Classement pour une configuration donnée
    configuration = request.GET.get('configuration', configurations[0] if configurations else 'G10A4')
    size, alignment_to_win = map(int, configuration[1:].split('A'))

    user_profiles = Profile.objects.all()
    scores_list = []

    for profile in user_profiles:
        scores = json.loads(profile.scores)
        if configuration in scores:
            scores_list.append((profile.user.username, scores[configuration]))

    scores_list = sorted(scores_list, key=lambda x: x[1], reverse=True)
    rank = next((i for i, score in enumerate(scores_list) if score[0] == user.username), None)

    context = {
        'days': days,
        'normal_games_played': normal_games_played,
        'tournament_games_played': tournament_games_played,
        'configurations': configurations,
        'selected_configuration': configuration,
        'rank': rank + 1 if rank is not None else 'N/A',
        'total_players': len(scores_list)
    }

    return render(request, 'blog/statistics.html', context)



@login_required
def join_tournament(request):
    # Récupérer ou créer le tournoi du jour
    tournament = Tournament.get_today_tournament()

    if tournament.is_full():
        messages.error(request, "Le tournoi d'aujourd'hui est complet. Revenez demain pour un nouveau tournoi.")
        return redirect('blog-home')

    if request.user in tournament.players.all():
        messages.info(request, "Vous êtes déjà inscrit à ce tournoi.")
    else:
        tournament.add_player(request.user)
        messages.success(request, "Vous avez rejoint le tournoi avec succès.")

    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    return render(request, 'blog/tournament_detail.html', {'tournament': tournament})

@login_required
def play_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    post = Post.objects.filter(tournament=tournament).first()
    players = list(tournament.players.all())
    if not post:
        post = Post.objects.create(
            title=tournament.name,
            size=tournament.grid_size,
            alignmentToWin=tournament.alignment_to_win,
            author=players[0],
            player2=players[1],
            player3=players[2],
            player4=players[3],
            current_player=players[0].username  # Le premier joueur commence
        )
        post.tournament = tournament
        post.save()
    else:
        # Vérifiez si `current_player` est `None` et définissez-le si nécessaire
        if not post.current_player:
            post.current_player = players[0].username
            post.save()

    # Sérialiser les informations des joueurs
    serialized_players = []
    for player in players:
        serialized_players.append({
            'id': player.id,
            'username': player.username
        })

    player_symbols = {
        'X': players[0].profile.symbol.url,
        'O': players[1].profile.symbol.url,
        'A': players[2].profile.symbol.url,
        'B': players[3].profile.symbol.url,
    }

    if post.gameOver:
        tournament.started = False  # Le tournoi est terminé
        tournament.save()

    return render(request, 'blog/play_tournament.html', {
        'post': post,
        'players': serialized_players,
        'player_symbols': player_symbols,
        'board': post.board
    })


def check_victory_tournament(board, player, alignment_to_win):
    size = len(board)

    def check_line(line):
        count = 0
        for cell in line:
            if cell == player:
                count += 1
                if count == alignment_to_win:
                    return True
            else:
                count = 0
        return False

    # Check rows
    for row in board:
        if check_line(row):
            print(f"Victory in row: {row}")
            return True

    # Check columns
    for col in range(size):
        column = [board[row][col] for row in range(size)]
        if check_line(column):
            print(f"Victory in column: {column}")
            return True

    # Check diagonals
    def check_diagonals(player):
        for row in range(size):
            for col in range(size):
                # Diagonale principale
                count_principal = 0
                count_inverse = 0
                for i in range(-alignment_to_win + 1, alignment_to_win):
                    r_principal, c_principal = row + i, col + i
                    r_inverse, c_inverse = row - i, col + i

                    if 0 <= r_principal < size and 0 <= c_principal < size and board[r_principal][c_principal] == player:
                        count_principal += 1
                        if count_principal == alignment_to_win:
                            print(f"Victory in principal diagonal starting at ({row},{col})")
                            return True
                    else:
                        count_principal = 0

                    if 0 <= r_inverse < size and 0 <= c_inverse < size and board[r_inverse][c_inverse] == player:
                        count_inverse += 1
                        if count_inverse == alignment_to_win:
                            print(f"Victory in inverse diagonal starting at ({row},{col})")
                            return True
                    else:
                        count_inverse = 0

        return False

    if check_diagonals(player):
        return True

    return False
@csrf_exempt
@login_required
def update_game_board(request, post_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            board = data.get('board')
            post = get_object_or_404(Post, id=post_id)
            post.board = board

            # Déterminer le joueur actuel et le joueur suivant
            players = [post.author, post.player2, post.player3, post.player4]
            player_usernames = [player.username for player in players if player]
            player_symbols = {
                post.author.username: 'X',
                post.player2.username: 'O',
                post.player3.username: 'A',
                post.player4.username: 'B'
            }

            current_player_index = player_usernames.index(post.current_player)
            current_symbol = player_symbols[post.current_player]
            next_player_index = (current_player_index + 1) % len(player_usernames)
            post.current_player = player_usernames[next_player_index]

            # Remplir le tableau avec les symboles
            for row in range(len(board)):
                for col in range(len(board[row])):
                    if board[row][col] in player_usernames:
                        board[row][col] = player_symbols[board[row][col]]

            # Vérifier les conditions de victoire
            if check_victory_tournament(board, current_symbol, post.alignmentToWin):
                post.winner_player = players[current_player_index]
                post.gameOver = True

                # Définir les perdants pour les tournois à quatre joueurs
                if len(player_usernames) > 2:
                    post.losers.set([player for player in players if player != post.winner_player])
                else:
                    post.loser_player = players[next_player_index]

                # Mettre à jour les scores des utilisateurs
                winner_profile = Profile.objects.get(user=post.winner_player)
                winner_profile.update_score(post.size, post.alignmentToWin)

                # Mettre fin au tournoi
                tournament = post.tournament
                if tournament:
                    tournament.started = False  # Marquer le tournoi comme terminé
                    tournament.save()

                post.save()
                return JsonResponse({
                    'status': 'success',
                    'current_player': post.current_player,
                    'gameOver': True,
                    'winner': post.winner_player.username,
                    'losers': [loser.username for loser in post.losers.all()] if len(player_usernames) > 2 else [post.loser_player.username]
                })

            post.save()
            return JsonResponse({'status': 'success', 'current_player': post.current_player})
        except Exception as e:
            print(f"Exception: {e}")  # Ajoutez cette ligne pour le débogage
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@login_required
def get_game_state_tournament(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    return JsonResponse({
        'board': post.board,
        'current_player': post.current_player,
        'gameOver': post.gameOver,
        'draw': post.draw,
        'winner': post.winner_player.username if post.winner_player else None,
        'losers': [loser.username for loser in post.losers.all()] if len(post.losers.all()) > 0 else [post.loser_player.username] if post.loser_player else []
    })
