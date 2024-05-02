from rest_framework import serializers
from .models import UserAccount


class AddUserSerializer(serializers.ModelSerializer):
    #userId = serializers.IntegerField() username = serializers.EmailField()
    # firstname = serializers.CharField()
    # lastname = serializers.CharField()
    class Meta:
        model = UserAccount
        fields = ['username', 'firstname', 'lastname']
    
class UserIdSerializer(serializers.Serializer):
    userId = serializers.IntegerField()
    
class EditUserSerializer(UserIdSerializer, AddUserSerializer):
    pass