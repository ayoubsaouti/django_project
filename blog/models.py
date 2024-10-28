from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
import random
import string

class Tournament(models.Model):
    name = models.CharField(max_length=100)
    players = models.ManyToManyField(User, related_name='tournaments')
    grid_size = models.PositiveIntegerField(default=12)
    alignment_to_win = models.PositiveIntegerField(default=3)
    date_created = models.DateTimeField(default=timezone.now)
    started = models.BooleanField(default=False)
    date_played = models.DateField(null=True, blank=True)  # Nouvelle colonne pour enregistrer la date du tournoi

    winner = models.ForeignKey(User, related_name='won_tournaments', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.name

    def add_player(self, user):
        if not self.is_full():
            self.players.add(user)
            if self.players.count() == 4:
                self.started = True
                self.date_played = timezone.now()
            self.save()
    def start_tournament(self):
        self.started = True
        self.date_played = timezone.now().date()
        self.save()

    def is_full(self):
        return self.players.count() >= 4

    @staticmethod
    def get_today_tournament():
        today = timezone.now().date()
        tournament = Tournament.objects.filter(date_created__date=today).first()
        if not tournament:
            tournament = Tournament.objects.create(name=f"Tournament {today.strftime('%Y-%m-%d')}")
        return tournament
class Post(models.Model):
    PUBLIC = 'PUBLIC'
    PRIVATE = 'PRIVATE'

    TYPE_CHOICES = [
        (PUBLIC, 'PUBLIC'),
        (PRIVATE, 'PRIVATE'),
    ]

    title = models.CharField(max_length=100)
    size = models.PositiveIntegerField(default=0)
    alignmentToWin = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=PUBLIC)
    max_moves = models.PositiveIntegerField(default=0)
    board = models.JSONField(default=list)
    access_code = models.CharField(max_length=10, blank=True, unique=True)
    date_posted = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_game')
    player2 = models.ForeignKey(User, related_name='joined_game', null=True, blank=True, on_delete=models.CASCADE)
    player3 = models.ForeignKey(User, related_name='joined_game_3', null=True, blank=True, on_delete=models.CASCADE)
    player4 = models.ForeignKey(User, related_name='joined_game_4', null=True, blank=True, on_delete=models.CASCADE)
    current_player = models.CharField(max_length=100, null=True, blank=True)
    winner_player = models.ForeignKey(User, related_name='winner', null=True, blank=True, on_delete=models.CASCADE)
    loser_player = models.ForeignKey(User, related_name='loser', null=True, blank=True, on_delete=models.CASCADE)
    losers = models.ManyToManyField(User, related_name='losers', blank=True)  # Ajouté pour les tournois
    draw = models.BooleanField(default=False)
    surrender = models.BooleanField(default=False)
    gameOver = models.BooleanField(default=False)
    moves_played = models.PositiveIntegerField(default=0)
    tournament = models.ForeignKey(Tournament, related_name='games', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('post-detail', kwargs={'pk': self.pk})

    def clean(self):
        # Vérifier que alignmentToWin est positif
        if self.alignmentToWin < 1:
            raise ValidationError('L\'alignement doit être d\'au moins 1.')

        # Calculer les limites de max_moves
        min_moves = 2 * self.alignmentToWin
        max_moves = 4 * self.alignmentToWin

        # Vérifier que max_moves est dans la plage valide
        if self.max_moves < min_moves or self.max_moves > max_moves:
            raise ValidationError(
                f'Le nombre maximum de coups doit être entre {min_moves} et {max_moves}.'
            )
    def generate_access_code(self):
        letters = string.ascii_uppercase
        digits = string.digits
        while True:
            access_code = ''.join(random.choices(letters, k=8)) + ''.join(random.choices(digits, k=2))
            if not Post.objects.filter(access_code=access_code).exists():
                break
        self.access_code = access_code
        return self.access_code

    def save(self, *args, **kwargs):
        if not self.access_code:
            self.generate_access_code()

        if not self.pk or Post.objects.get(pk=self.pk).size != self.size:
            self.board = [["" for _ in range(self.size)] for _ in range(self.size)]

        super().save(*args, **kwargs)

def generate_board(size):
    return [['' for _ in range(size)] for _ in range(size)]

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Post)
def initialize_board(sender, instance, created, **kwargs):
    if created and not instance.board:
        instance.board = generate_board(instance.size)
        instance.save()
