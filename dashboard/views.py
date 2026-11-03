from django.shortcuts import render


def home(request):
    return render(request, 'dashboard/home.html')


def profile(request):
    return render(request, 'dashboard/profile.html')


def settings(request):
    return render(request, 'dashboard/settings.html')
