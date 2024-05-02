from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from .models import UserAccount
from .serializers import AddUserSerializer, UserIdSerializer, EditUserSerializer

# Create your views here.


class GetUserView(APIView):
    
    def get(self, request):
        data = UserAccount.objects.all().values()
        return Response(data)
    
class AddUserView(GenericAPIView):
    serializer_class = AddUserSerializer
    
    def post(self, request):
        deserilaizer = self.serializer_class(data = request.data)
        deserilaizer.is_valid(raise_exception = True)
        
        user_name = deserilaizer.validated_data.get('username')
        first_name = deserilaizer.validated_data.get('firstname')
        last_name = deserilaizer.validated_data.get('firstname')
        
        UserAccount.objects.create(username = user_name, firstname = first_name, lastname = last_name)
        return Response('User Created.')
    
class DeleteUserView(GenericAPIView):
    serializer_class =  UserIdSerializer
    
    def post(self, request):
        deserializer = self.serializer_class(data = request.data)
        deserializer.is_valid(raise_exception = True)
        
        print('validated json', deserializer.validated_data)
        user_id = deserializer.validated_data.get('userId')
        user = UserAccount.objects.filter(id = user_id)
        if not user:
            return Response('No such a user')
        else:
            user.first().delete()
            return Response('User deleted.')
        
class UpdateUserView(GenericAPIView):
    serializer_class = EditUserSerializer
    
    def post(self, request):
        deserializer = self.serializer_class(data = request.data)
        deserializer.is_valid(raise_exception = True)
        
        userId = deserializer.validated_data.get('userId')
        user_name = deserializer.validated_data.get('username')
        first_name = deserializer.validated_data.get('firstname')
        last_name = deserializer.validated_data.get('lastname')
        
        user = UserAccount.objects.filter(id = userId)
        if not user:
            return Response('Invalid user id')
        else:
            current_user = user.first()
            current_user.firstname = first_name
            current_user.lastname = last_name
            current_user.username = user_name
            current_user.save()
            return Response('User Updated')