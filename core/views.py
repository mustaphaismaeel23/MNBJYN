from django.shortcuts import redirect, render

from . import content
from .forms import RegistrationForm
from .lga_data import lga_json_data
from django.http import Http404, HttpResponse
from django.views.decorators.cache import cache_control

from .models import Executive, GalleryImage, StoredFile, TeamMember


def home(request):
    from .lga_data import STATE_CODE, STATE_NAME
    from .models import SituationRoomConfig

    lga_data = lga_json_data()
    try:
        situation = SituationRoomConfig.load()
        mode, refresh = situation.mode, situation.refresh_seconds
    except Exception:   # never let the Situation Room settings take the home page down
        mode, refresh = "simulation", 10
    context = {
        "situation_config": {
            "mode": mode,
            "refresh_seconds": refresh,
            "state_code": STATE_CODE,
            "state_name": STATE_NAME,
            "lga_count": len(lga_data),
            "api": "/api/v1",
        },
        "content": content,
        "gallery": GalleryImage.objects.filter(is_published=True)[:12],
        "gallery_fallback": [
            {
                "image": "core/img/gallery/nasiru-bala-jaoji-speaking.jpg",
                "caption": "Malam Nasiru Bala Ja'oji speaking at an event",
            },
            {
                "image": "core/img/gallery/nasiru-bala-jaoji-gathering.jpg",
                "caption": "Malam Nasiru Bala Ja'oji at a gathering",
            },
            {
                "image": "core/img/gallery/nasiru-bala-jaoji-event.jpg",
                "caption": "Malam Nasiru Bala Ja'oji at an event",
            },
            {
                "image": "core/img/gallery/nasiru-bala-jaoji-portrait.jpg",
                "caption": "Malam Nasiru Bala Ja'oji",
            },
            {
                "image": "core/img/gallery/nasiru-bala-jaoji-address.jpg",
                "caption": "Malam Nasiru Bala Ja'oji addressing a gathering",
            },
        ],
        "gallery_placeholders": range(6),
        "lga_data": lga_data,
        "lga_count": len(lga_data),
        "executives": Executive.objects.filter(is_published=True),
        "team": TeamMember.objects.filter(is_published=True),
    }
    return render(request, "core/home.html", context)


@cache_control(public=True, max_age=86400)
def media(request, name):
    """Serve an uploaded file stored in the database."""
    if name.startswith("sheets/"):      # private result-sheet photos: only via the API
        raise Http404
    try:
        f = StoredFile.objects.get(name=name)
    except StoredFile.DoesNotExist:
        raise Http404
    return HttpResponse(bytes(f.data), content_type=f.content_type)


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            registration = form.save()
            request.session["last_registration"] = {
                "name": registration.full_name.split()[0],
                "ref": registration.reference,
            }
            return redirect("core:thank_you")
    else:
        form = RegistrationForm()
    return render(request, "core/register.html", {"form": form, "lga_data": lga_json_data()})


def thank_you(request):
    info = request.session.get("last_registration")
    if not info:
        return redirect("core:register")
    return render(request, "core/thank_you.html", {"info": info})


# Dedicated authentication screens for the custom MNBJYN admin workspace.
def mainadmin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("core:mainadmin")
    error = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active and user.is_staff:
            login(request, user)
            destination = request.GET.get("next", "")
            # Only allow local admin destinations to prevent open redirects.
            if destination.startswith("/mainadmin/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect("core:mainadmin")
        error = "The username or password is incorrect, or this account is not authorized."
    return render(request, "core/mainadmin_login.html", {"error": error})


def mainadmin_logout(request):
    if request.method == "POST":
        logout(request)
    return redirect("core:mainadmin_login")


# Private, staff-only member management workspace.
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Registration
from django import forms


class MemberAdminForm(forms.ModelForm):
    class Meta:
        model = Registration
        exclude = ("created_at", "updated_at")
        widgets = {"message": forms.Textarea(attrs={"rows": 3}),
                   "admin_notes": forms.Textarea(attrs={"rows": 3})}


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="/mainadmin/login/", redirect_field_name="next")
def mainadmin(request):
    qs = Registration.objects.all()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    lga = request.GET.get("lga", "").strip()
    if query:
        from django.db.models import Q
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) |
                       Q(email__icontains=query) | Q(ward__icontains=query))
    if status:
        qs = qs.filter(status=status)
    if lga:
        qs = qs.filter(lga=lga)
    from .models import LGA_CHOICES
    return render(request, "core/mainadmin.html", {
        "members": qs[:250], "total": Registration.objects.count(),
        "shown": qs.count(), "new_count": Registration.objects.filter(status="new").count(),
        "approved_count": Registration.objects.filter(status="approved").count(),
        "query": query, "status_filter": status, "lga_filter": lga,
        "statuses": Registration.Status.choices, "lgas": LGA_CHOICES,
    })


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="/mainadmin/login/", redirect_field_name="next")
def mainadmin_create(request):
    form = MemberAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        messages.success(request, f"{member.full_name} was added.")
        return redirect("core:mainadmin")
    return render(request, "core/member_form.html", {"form": form, "heading": "Add member", "editing": False})


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="/mainadmin/login/", redirect_field_name="next")
def mainadmin_edit(request, pk):
    member = get_object_or_404(Registration, pk=pk)
    form = MemberAdminForm(request.POST or None, instance=member)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{member.full_name} was updated.")
        return redirect("core:mainadmin")
    return render(request, "core/member_form.html", {"form": form, "heading": "Edit member", "editing": True, "member": member})


@user_passes_test(lambda user: user.is_authenticated and user.is_staff, login_url="/mainadmin/login/", redirect_field_name="next")
def mainadmin_delete(request, pk):
    member = get_object_or_404(Registration, pk=pk)
    if request.method == "POST":
        name = member.full_name
        member.delete()
        messages.success(request, f"{name} was deleted.")
        return redirect("core:mainadmin")
    return render(request, "core/member_confirm_delete.html", {"member": member})
