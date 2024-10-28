from django.db import models
from django.contrib.auth.models import User
from PIL import Image
import json

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(default='default.jpg', upload_to='profile_pics')
    symbol = models.ImageField(default='cercle.jpg', upload_to='symbols')
    scores = models.TextField(default='{}')  # Utilisez TextField pour stocker les scores JSON

    def __str__(self):
        return f'{self.user.username} Profile'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        img = Image.open(self.image.path)
        img2 = Image.open(self.symbol.path)

        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.image.path)

        if img2.height > 300 or img2.width > 300:
            output_size = (50, 50)
            img2.thumbnail(output_size)
            img2.save(self.symbol.path)

    def update_score(self, size, alignment_to_win):
        scores = json.loads(self.scores)  # Charger les scores existants
        key = f"G{size}A{alignment_to_win}"
        if key in scores:
            scores[key] += 1
        else:
            scores[key] = 1
        self.scores = json.dumps(scores)  # Sauvegarder les scores mis à jour
        self.save()

    def get_scores(self):
        return json.loads(self.scores).items()  # Retourner les scores sous forme d'éléments