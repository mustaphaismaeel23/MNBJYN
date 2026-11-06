from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("mainadmin/login/", views.mainadmin_login, name="mainadmin_login"),
    path("mainadmin/logout/", views.mainadmin_logout, name="mainadmin_logout"),
    path("mainadmin/", views.mainadmin, name="mainadmin"),
    path("mainadmin/members/add/", views.mainadmin_create, name="mainadmin_create"),
    path("mainadmin/members/<int:pk>/edit/", views.mainadmin_edit, name="mainadmin_edit"),
    path("mainadmin/members/<int:pk>/delete/", views.mainadmin_delete, name="mainadmin_delete"),
    path("register/", views.register, name="register"),
    path("register/thank-you/", views.thank_you, name="thank_you"),
]
