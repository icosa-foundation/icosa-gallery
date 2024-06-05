import requests
from api.models import User as IcosaUser

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.shortcuts import redirect, render


def custom_login(request):
    if request.method == "POST":
        username = request.POST.get("username", None)
        password = request.POST.get("password", None)
        user_is_authenticated = False

        if username is not None and password is not None:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                user_is_authenticated = True
            else:
                # Authenticate with fastapi and try to create a django user

                response = requests.post(
                    "http://api-fastapi:8000/login",
                    data={
                        "username": username,
                        "password": password,
                    },
                    verify=False,
                )
                status = response.status_code
                if status == 200:
                    # Auth succeeded, create the user for django
                    User.objects.create_user(
                        username=username,
                        email=username,
                        password=password,
                    )
                    user = authenticate(
                        request, username=username, password=password
                    )
                    if user is not None:
                        try:
                            icosa_user = IcosaUser.objects.get(email=username)
                            icosa_user.migrated = True
                            icosa_user.save()
                        except IcosaUser.DoesNotExist:
                            pass
                        user_is_authenticated = True

        if user_is_authenticated is True:
            login(request, user)
            return redirect("home")
        else:
            return render(
                request,
                "auth/login.html",
                {"error": "Invalid username or password"},
            )
    else:
        return render(request, "auth/login.html")


def custom_logout(request):
    if request.method == "POST":
        logout(request)
        return redirect("home")
    else:
        return render(request, "auth/logout.html")
