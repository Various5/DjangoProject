from .models import UserProfile

def current_theme(request):
    if request.user.is_authenticated:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        return {'current_theme': profile.theme}
    return {'current_theme': 'dark'}
