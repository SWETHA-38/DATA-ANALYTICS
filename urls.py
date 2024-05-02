from django.urls import path

from .views import GetUserView, AddUserView, DeleteUserView, UpdateUserView

urlpatterns = [
    path('getUser/', GetUserView.as_view()),
    path('addUser/', AddUserView.as_view()),
    path('deleteUser/', DeleteUserView.as_view()),
    path('updateUser/', UpdateUserView.as_view())
]