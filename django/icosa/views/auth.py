import secrets
import string
from datetime import datetime, timedelta

import requests
from icosa.models import DeviceCode
from icosa.models import User as IcosaUser

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render


def generate_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(
        set(string.ascii_uppercase + string.digits) - set(exclude)
    )
    return "".join(secrets.choice(characters) for i in range(length))


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


def devicecode(request):
    template = "auth/device.html"
    user = request.user
    context = {}
    if user.is_authenticated:
        owner = IcosaUser.from_request(request)
        code = generate_code()
        expiry_time = datetime.utcnow() + timedelta(minutes=1)

        # Delete all codes for this user
        DeviceCode.objects.filter(user=owner).delete()
        # Delete all expired codes for any user
        DeviceCode.objects.filter(expiry__lt=datetime.utcnow()).delete()

        DeviceCode.objects.create(
            user=owner,
            devicecode=code,
            expiry=expiry_time,
        )

        context = {
            "device_code": code.upper(),
        }
    return render(request, template, context)
