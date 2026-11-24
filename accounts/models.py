from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Shop owners and staff. A custom model from day one, so it can grow without a rewrite."""

    email = models.EmailField(unique=True)
