from django.db import models

# Create your models here.

class UserAccount(models.Model):
    username = models.EmailField()
    firstname = models.CharField(max_length = 100)
    lastname = models.CharField(max_length = 100)
    is_active = models.BooleanField(default = True)
    demo = models.CharField(max_length = 100, default = 'Test')
    
    class Meta:
        db_table = 'useraccount'
    