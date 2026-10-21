from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import connection, IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.db import transaction
from django.core.paginator import Paginator
from apps.forms import *
from apps.models import *
from authentication.decorators import role_required, edit_required
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta
import datetime


def _ctx(request, segment, group_segment, crud, menu_id, extra=None):
    """Context baku halaman: role menu & hak akses tombol untuk user berjalan."""
    context = {
        'segment': segment,
        'group_segment': group_segment,
        'crud': crud,
        'role': Auth.objects.filter(user_id=request.user.user_id).values_list(
            'menu_id', flat=True),
        'btn': Auth.objects.filter(
            user_id=request.user.user_id, menu_id=menu_id).first()
        if not request.user.is_superuser else Auth.objects.all(),
    }
    if extra:
        context.update(extra)
    return context


def _next_number(prefix, model, field, date_value=None):
    """Generator nomor dokumen sederhana: PREFIX+YYYYMMDD+urutan harian."""
    today = date_value or timezone.now().date()
    counter = model.objects.filter(
        **{f'{field}__startswith': f'{prefix}{today:%Y%m%d}'}).count() + 1
    return f'{prefix}{today:%Y%m%d}{counter:03d}'


# =============================================================================
# Dashboard
# =============================================================================

@login_required(login_url='/login/')
def home(request):
    today = timezone.now().date()
    upcoming = Keberangkatan.objects.filter(
        tanggal_berangkat__gte=today,
        status__in=['OPEN', 'PREPARATION'],
    ).select_related('paket').order_by('tanggal_berangkat')[:5]

    stats = {
        'total_jamaah': Jamaah.objects.count(),
        'total_paket': Paket.objects.filter(status='ACTIVE').count(),
        'booking_aktif': Booking.objects.exclude(
            status__in=['CANCELED', 'COMPLETED']).count(),
        'keberangkatan_depan': upcoming.count(),
        'pendapatan': Pembayaran.objects.filter(status='VERIFIED').aggregate(
            total=Sum('nominal'))['total'] or 0,
        'belum_verifikasi': Pembayaran.objects.filter(status='PENDING').count(),
    }

    return render(request, 'home/index.html', _ctx(
        request, 'index', 'dashboard', 'index', 'DASHBOARD',
        {'stats': stats, 'upcoming': upcoming}))


# =============================================================================
# Pengguna
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def user_index(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id, username, email, position_name FROM apps_user INNER JOIN apps_position ON apps_user.position_id = apps_position.position_id")
        users = cursor.fetchall()

    return render(request, 'home/user_index.html',
                  _ctx(request, 'user', 'master', 'index', 'USER', {'data': users}))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def user_add(request):
    position = Position.objects.all()
    if request.POST:
        form = FormUser(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('user-view', args=[form.instance.user_id, ]))
        else:
            return render(request, 'home/user_add.html', _ctx(
                request, 'user', 'master', 'add', 'USER',
                {'form': form, 'position': position, 'message': form.errors}))
    else:
        form = FormUser()
        return render(request, 'home/user_add.html', _ctx(
            request, 'user', 'master', 'add', 'USER',
            {'form': form, 'position': position}))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def user_view(request, _id):
    users = User.objects.get(user_id=_id)
    auth = Auth.objects.filter(user_id=_id)
    form = FormUserView(instance=users)
    position = Position.objects.all()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT apps_menu.menu_id, menu_name, q_auth.menu_id FROM apps_menu LEFT JOIN (SELECT * FROM apps_auth WHERE user_id = '" + str(_id) + "') AS q_auth ON apps_menu.menu_id = q_auth.menu_id WHERE q_auth.menu_id IS NULL")
        menu = cursor.fetchall()

    if request.POST:
        check = request.POST.getlist('checks[]')
        for i in menu:
            if str(i[0]) in check:
                try:
                    auth = Auth(user_id=_id, menu_id=i[0])
                    auth.save()
                except IntegrityError:
                    continue
            else:
                Auth.objects.filter(user_id=_id, menu_id=i[0]).delete()

        return HttpResponseRedirect(reverse('user-view', args=[_id, ]))

    return render(request, 'home/user_view.html', _ctx(
        request, 'user', 'master', 'view', 'USER',
        {'form': form, 'formAuth': form, 'data': users, 'auth': auth,
         'menu': menu, 'positions': position, 'tab': 'auth'}))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def auth_update(request, _id, _menu):
    auth = Auth.objects.get(user=_id, menu=_menu)

    if request.POST:
        auth.add = 1 if request.POST.get('add') else 0
        auth.edit = 1 if request.POST.get('edit') else 0
        auth.delete = 1 if request.POST.get('delete') else 0
        auth.save()

        return HttpResponseRedirect(reverse('user-view', args=[_id, ]))

    return render(request, 'home/user_view.html')


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def auth_delete(request, _id, _menu):
    auth = Auth.objects.filter(user=_id, menu=_menu)

    auth.delete()
    return HttpResponseRedirect(reverse('user-view', args=[_id, ]))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def remove_signature(request, _id):
    users = User.objects.get(user_id=_id)
    users.signature = None
    users.save()
    return HttpResponseRedirect(reverse('user-view', args=[_id, ]))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def user_update(request, _id):
    users = User.objects.get(user_id=_id)
    position = Position.objects.all()
    auth = Auth.objects.filter(user_id=_id)

    if request.POST:
        form = FormUserUpdate(request.POST, request.FILES, instance=users)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('user-view', args=[_id, ]))
    else:
        form = FormUserUpdate(instance=users)

    return render(request, 'home/user_view.html', _ctx(
        request, 'user', 'master', 'update', 'USER',
        {'form': form, 'data': users, 'positions': position,
         'auth': auth, 'tab': 'auth', 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def user_delete(request, _id):
    users = User.objects.get(user_id=_id)

    users.delete()
    return HttpResponseRedirect(reverse('user-index'))


@login_required(login_url='/login/')
def change_password(request):
    if request.POST:
        form = FormChangePassword(data=request.POST, user=request.user)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            return HttpResponseRedirect(reverse('home'))
    else:
        form = FormChangePassword(user=request.user)

    return render(request, 'home/user_change_password.html', _ctx(
        request, 'user', 'master', 'update', 'USER',
        {'form': form, 'data': request.user, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='USER')
def set_password(request, _id):
    users = User.objects.get(user_id=_id)
    if request.POST:
        form = FormSetPassword(data=request.POST, user=users)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            return HttpResponseRedirect(reverse('user-view', args=[_id, ]))
    else:
        form = FormSetPassword(user=users)

    return render(request, 'home/user_set_password.html', _ctx(
        request, 'user', 'master', 'update', 'USER',
        {'form': form, 'data': users, 'message': form.errors}))


# =============================================================================
# Posisi
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='POSITION')
def position_add(request):
    if request.POST:
        form = FormPosition(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('position-index'))
        else:
            return render(request, 'home/position_add.html', _ctx(
                request, 'position', 'master', 'add', 'POSITION',
                {'form': form, 'message': form.errors}))
    else:
        form = FormPosition()
        return render(request, 'home/position_add.html', _ctx(
            request, 'position', 'master', 'add', 'POSITION', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='POSITION')
def position_index(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT position_id, position_name FROM apps_position")
        positions = cursor.fetchall()

    return render(request, 'home/position_index.html',
                  _ctx(request, 'position', 'master', 'index', 'POSITION',
                       {'data': positions}))


@login_required(login_url='/login/')
@role_required(allowed_roles='POSITION')
def position_update(request, _id):
    positions = Position.objects.get(position_id=_id)
    if request.POST:
        form = FormPositionUpdate(
            request.POST, request.FILES, instance=positions)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('position-view', args=[_id, ]))
    else:
        form = FormPositionUpdate(instance=positions)

    return render(request, 'home/position_view.html', _ctx(
        request, 'position', 'master', 'update', 'POSITION',
        {'form': form, 'data': positions, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='POSITION')
def position_delete(request, _id):
    positions = Position.objects.get(position_id=_id)

    positions.delete()
    return HttpResponseRedirect(reverse('position-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='POSITION')
def position_view(request, _id):
    positions = Position.objects.get(position_id=_id)
    form = FormPositionView(instance=positions)

    return render(request, 'home/position_view.html', _ctx(
        request, 'position', 'master', 'view', 'POSITION',
        {'form': form, 'data': positions}))


# =============================================================================
# Menu
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='MENU')
def menu_index(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT menu_id, menu_name, menu_remark FROM apps_menu")
        menus = cursor.fetchall()

    return render(request, 'home/menu_index.html',
                  _ctx(request, 'menu', 'master', 'index', 'MENU', {'data': menus}))


@login_required(login_url='/login/')
@role_required(allowed_roles='MENU')
def menu_add(request):
    if request.POST:
        form = FormMenu(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('menu-view', args=[form.instance.menu_id, ]))
        else:
            return render(request, 'home/menu_add.html', _ctx(
                request, 'menu', 'master', 'add', 'MENU',
                {'form': form, 'message': form.errors}))
    else:
        form = FormMenu()
        return render(request, 'home/menu_add.html', _ctx(
            request, 'menu', 'master', 'add', 'MENU', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='MENU')
def menu_update(request, _id):
    menus = Menu.objects.get(menu_id=_id)
    if request.POST:
        form = FormMenuUpdate(request.POST, request.FILES, instance=menus)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('menu-view', args=[_id, ]))
    else:
        form = FormMenuUpdate(instance=menus)

    return render(request, 'home/menu_view.html', _ctx(
        request, 'menu', 'master', 'update', 'MENU',
        {'form': form, 'data': menus, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='MENU')
def menu_delete(request, _id):
    menus = Menu.objects.get(menu_id=_id)

    menus.delete()
    return HttpResponseRedirect(reverse('menu-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='MENU')
def menu_view(request, _id):
    menus = Menu.objects.get(menu_id=_id)
    form = FormMenuView(instance=menus)

    return render(request, 'home/menu_view.html', _ctx(
        request, 'menu', 'master', 'view', 'MENU',
        {'form': form, 'data': menus}))


# =============================================================================
# Agen
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='AGEN')
def agen_index(request):
    data = Agen.objects.all().order_by('agen_id')

    return render(request, 'home/agen_index.html',
                  _ctx(request, 'agen', 'master', 'index', 'AGEN', {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='AGEN')
def agen_add(request):
    if request.POST:
        form = FormAgen(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('agen-view', args=[form.instance.agen_id, ]))
        else:
            return render(request, 'home/agen_add.html', _ctx(
                request, 'agen', 'master', 'add', 'AGEN',
                {'form': form, 'message': form.errors}))
    else:
        form = FormAgen()
        return render(request, 'home/agen_add.html', _ctx(
            request, 'agen', 'master', 'add', 'AGEN', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='AGEN')
def agen_update(request, _id):
    agen = get_object_or_404(Agen, agen_id=_id)
    if request.POST:
        form = FormAgenUpdate(request.POST, request.FILES, instance=agen)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('agen-view', args=[_id, ]))
    else:
        form = FormAgenUpdate(instance=agen)

    return render(request, 'home/agen_view.html', _ctx(
        request, 'agen', 'master', 'update', 'AGEN',
        {'form': form, 'data': agen, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='AGEN')
def agen_delete(request, _id):
    agen = get_object_or_404(Agen, agen_id=_id)
    try:
        agen.delete()
    except ProtectedError:
        form = FormAgenView(instance=agen)
        return render(request, 'home/agen_view.html', _ctx(
            request, 'agen', 'master', 'view', 'AGEN',
            {'form': form, 'data': agen,
             'message': 'Agen ini sudah dipakai pada data booking dan tidak bisa dihapus.'}))

    return HttpResponseRedirect(reverse('agen-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='AGEN')
def agen_view(request, _id):
    agen = get_object_or_404(Agen, agen_id=_id)
    form = FormAgenView(instance=agen)
    bookings = Booking.objects.filter(agen=agen).select_related(
        'jamaah', 'keberangkatan').order_by('-tanggal_booking')[:20]

    return render(request, 'home/agen_view.html', _ctx(
        request, 'agen', 'master', 'view', 'AGEN',
        {'form': form, 'data': agen, 'bookings': bookings}))


# =============================================================================
# Paket
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='PAKET')
def paket_index(request):
    data = Paket.objects.all().order_by('paket_id')

    return render(request, 'home/paket_index.html',
                  _ctx(request, 'paket', 'master', 'index', 'PAKET', {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='PAKET')
def paket_add(request):
    if request.POST:
        form = FormPaket(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('paket-view', args=[form.instance.paket_id, ]))
        else:
            return render(request, 'home/paket_add.html', _ctx(
                request, 'paket', 'master', 'add', 'PAKET',
                {'form': form, 'message': form.errors}))
    else:
        form = FormPaket()
        return render(request, 'home/paket_add.html', _ctx(
            request, 'paket', 'master', 'add', 'PAKET', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='PAKET')
def paket_update(request, _id):
    paket = get_object_or_404(Paket, paket_id=_id)
    if request.POST:
        form = FormPaketUpdate(request.POST, request.FILES, instance=paket)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('paket-view', args=[_id, ]))
    else:
        form = FormPaketUpdate(instance=paket)

    return render(request, 'home/paket_view.html', _ctx(
        request, 'paket', 'master', 'update', 'PAKET',
        {'form': form, 'data': paket, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='PAKET')
def paket_delete(request, _id):
    paket = get_object_or_404(Paket, paket_id=_id)
    try:
        paket.delete()
    except ProtectedError:
        form = FormPaketView(instance=paket)
        return render(request, 'home/paket_view.html', _ctx(
            request, 'paket', 'master', 'view', 'PAKET',
            {'form': form, 'data': paket,
             'message': 'Paket ini sudah dipakai pada data keberangkatan dan tidak bisa dihapus.'}))

    return HttpResponseRedirect(reverse('paket-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='PAKET')
def paket_view(request, _id):
    paket = get_object_or_404(Paket, paket_id=_id)
    form = FormPaketView(instance=paket)
    keberangkatans = Keberangkatan.objects.filter(
        paket=paket).order_by('-tanggal_berangkat')[:20]

    return render(request, 'home/paket_view.html', _ctx(
        request, 'paket', 'master', 'view', 'PAKET',
        {'form': form, 'data': paket, 'keberangkatans': keberangkatans}))


# =============================================================================
# Jamaah
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='JAMAAH')
def jamaah_index(request):
    data = Jamaah.objects.all().order_by('kode_jamaah')

    return render(request, 'home/jamaah_index.html',
                  _ctx(request, 'jamaah', 'operasional', 'index', 'JAMAAH',
                       {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='JAMAAH')
def jamaah_add(request):
    if request.POST:
        form = FormJamaah(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('jamaah-view', args=[form.instance.jamaah_id, ]))
        else:
            return render(request, 'home/jamaah_add.html', _ctx(
                request, 'jamaah', 'operasional', 'add', 'JAMAAH',
                {'form': form, 'message': form.errors}))
    else:
        next_code = f'JM{(Jamaah.objects.count() or 0) + 1:04d}'
        form = FormJamaah(initial={'kode_jamaah': next_code})
        return render(request, 'home/jamaah_add.html', _ctx(
            request, 'jamaah', 'operasional', 'add', 'JAMAAH', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='JAMAAH')
def jamaah_update(request, _id):
    jamaah = get_object_or_404(Jamaah, jamaah_id=_id)
    if request.POST:
        form = FormJamaahUpdate(request.POST, request.FILES, instance=jamaah)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('jamaah-view', args=[_id, ]))
    else:
        form = FormJamaahUpdate(instance=jamaah)

    return render(request, 'home/jamaah_view.html', _ctx(
        request, 'jamaah', 'operasional', 'update', 'JAMAAH',
        {'form': form, 'data': jamaah, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='JAMAAH')
def jamaah_delete(request, _id):
    jamaah = get_object_or_404(Jamaah, jamaah_id=_id)
    try:
        jamaah.delete()
    except ProtectedError:
        form = FormJamaahView(instance=jamaah)
        return render(request, 'home/jamaah_view.html', _ctx(
            request, 'jamaah', 'operasional', 'view', 'JAMAAH',
            {'form': form, 'data': jamaah,
             'message': 'Jamaah ini sudah memiliki data booking dan tidak bisa dihapus.'}))

    return HttpResponseRedirect(reverse('jamaah-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='JAMAAH')
def jamaah_view(request, _id):
    jamaah = get_object_or_404(Jamaah, jamaah_id=_id)
    form = FormJamaahView(instance=jamaah)
    bookings = Booking.objects.filter(jamaah=jamaah).select_related(
        'keberangkatan', 'agen').order_by('-tanggal_booking')

    return render(request, 'home/jamaah_view.html', _ctx(
        request, 'jamaah', 'operasional', 'view', 'JAMAAH',
        {'form': form, 'data': jamaah, 'bookings': bookings}))


# =============================================================================
# Keberangkatan
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='KEBERANGKATAN')
def keberangkatan_index(request):
    data = Keberangkatan.objects.select_related(
        'paket').order_by('-tanggal_berangkat')

    return render(request, 'home/keberangkatan_index.html', _ctx(
        request, 'keberangkatan', 'operasional', 'index', 'KEBERANGKATAN',
        {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='KEBERANGKATAN')
def keberangkatan_add(request):
    if request.POST:
        form = FormKeberangkatan(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('keberangkatan-view', args=[form.instance.keberangkatan_id, ]))
        else:
            return render(request, 'home/keberangkatan_add.html', _ctx(
                request, 'keberangkatan', 'operasional', 'add', 'KEBERANGKATAN',
                {'form': form, 'message': form.errors}))
    else:
        form = FormKeberangkatan()
        return render(request, 'home/keberangkatan_add.html', _ctx(
            request, 'keberangkatan', 'operasional', 'add', 'KEBERANGKATAN',
            {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='KEBERANGKATAN')
def keberangkatan_update(request, _id):
    keberangkatan = get_object_or_404(Keberangkatan, keberangkatan_id=_id)
    if request.POST:
        form = FormKeberangkatanUpdate(
            request.POST, request.FILES, instance=keberangkatan)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('keberangkatan-view', args=[_id, ]))
    else:
        form = FormKeberangkatanUpdate(instance=keberangkatan)

    return render(request, 'home/keberangkatan_view.html', _ctx(
        request, 'keberangkatan', 'operasional', 'update', 'KEBERANGKATAN',
        {'form': form, 'data': keberangkatan, 'message': form.errors}))


@login_required(login_url='/login/')
@role_required(allowed_roles='KEBERANGKATAN')
def keberangkatan_delete(request, _id):
    keberangkatan = get_object_or_404(Keberangkatan, keberangkatan_id=_id)
    try:
        keberangkatan.delete()
    except ProtectedError:
        form = FormKeberangkatanView(instance=keberangkatan)
        return render(request, 'home/keberangkatan_view.html', _ctx(
            request, 'keberangkatan', 'operasional', 'view', 'KEBERANGKATAN',
            {'form': form, 'data': keberangkatan,
             'message': 'Keberangkatan ini sudah memiliki data booking dan tidak bisa dihapus.'}))

    return HttpResponseRedirect(reverse('keberangkatan-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='KEBERANGKATAN')
def keberangkatan_view(request, _id):
    keberangkatan = get_object_or_404(Keberangkatan, keberangkatan_id=_id)
    form = FormKeberangkatanView(instance=keberangkatan)
    bookings = Booking.objects.filter(keberangkatan=keberangkatan).select_related(
        'jamaah', 'agen').order_by('nomor_booking')

    return render(request, 'home/keberangkatan_view.html', _ctx(
        request, 'keberangkatan', 'operasional', 'view', 'KEBERANGKATAN',
        {'form': form, 'data': keberangkatan, 'bookings': bookings}))


# =============================================================================
# Booking
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
def booking_index(request):
    data = Booking.objects.select_related(
        'jamaah', 'keberangkatan', 'keberangkatan__paket', 'agen'
    ).order_by('-tanggal_booking', '-booking_id')

    return render(request, 'home/booking_index.html',
                  _ctx(request, 'booking', 'operasional', 'index', 'BOOKING',
                       {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
@transaction.atomic
def booking_add(request):
    if request.POST:
        form = FormBooking(request.POST, request.FILES)
        if form.is_valid():
            keberangkatan = form.cleaned_data['keberangkatan']
            if keberangkatan.status not in ('OPEN',):
                form.add_error(
                    'keberangkatan',
                    'Pendaftaran hanya diterima pada keberangkatan berstatus Open.')
            elif timezone.now().date() > (
                    keberangkatan.batas_pendaftaran or keberangkatan.tanggal_berangkat):
                form.add_error('keberangkatan', 'Pendaftaran sudah ditutup.')
            elif keberangkatan.kursi_tersedia <= 0:
                form.add_error('keberangkatan', 'Kursi pada keberangkatan ini sudah penuh.')

            if not form.errors:
                booking = form.save(commit=False)
                booking.nomor_booking = _next_number('BK', Booking, 'nomor_booking')
                if not booking.harga:
                    booking.harga = booking.keberangkatan.paket.harga
                booking.save()

                # Invoice dibuat otomatis dari snapshot harga booking.
                invoice = Invoice(
                    nomor_invoice=_next_number('INV', Invoice, 'nomor_invoice'),
                    booking=booking,
                    tanggal_invoice=booking.tanggal_booking,
                    jatuh_tempo=booking.tanggal_booking + timedelta(days=14),
                    total=booking.harga,
                    status='UNPAID',
                )
                invoice.save()

                if keberangkatan.kursi_tersedia <= 0:
                    keberangkatan.status = 'FULL'
                    keberangkatan.save()

                return HttpResponseRedirect(reverse('booking-view', args=[booking.booking_id, ]))

        return render(request, 'home/booking_add.html', _ctx(
            request, 'booking', 'operasional', 'add', 'BOOKING',
            {'form': form, 'message': form.errors}))
    else:
        form = FormBooking(initial={'tanggal_booking': timezone.now().date()})
        return render(request, 'home/booking_add.html', _ctx(
            request, 'booking', 'operasional', 'add', 'BOOKING', {'form': form}))


@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
def booking_update(request, _id):
    booking = get_object_or_404(Booking, booking_id=_id)
    if request.POST:
        form = FormBookingUpdate(request.POST, request.FILES, instance=booking)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('booking-view', args=[_id, ]))
    else:
        form = FormBookingUpdate(instance=booking)

    return render(request, 'home/booking_view.html', _ctx(
        request, 'booking', 'operasional', 'update', 'BOOKING',
        {'form': form, 'data': booking, 'message': form.errors,
         'invoices': booking.invoices.all()}))


@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
def booking_delete(request, _id):
    booking = get_object_or_404(Booking, booking_id=_id)
    try:
        booking.delete()
    except ProtectedError:
        form = FormBookingView(instance=booking)
        return render(request, 'home/booking_view.html', _ctx(
            request, 'booking', 'operasional', 'view', 'BOOKING',
            {'form': form, 'data': booking, 'invoices': booking.invoices.all(),
             'message': 'Booking ini memiliki invoice/pembayaran dan tidak bisa dihapus. Gunakan Pembatalan untuk melepas kursi.'}))

    return HttpResponseRedirect(reverse('booking-index'))


@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
@edit_required('BOOKING')
@transaction.atomic
def booking_cancel(request, _id):
    booking = get_object_or_404(
        Booking.objects.select_for_update(), booking_id=_id)
    if booking.status != 'CANCELED':
        booking.status = 'CANCELED'
        booking.save()
        # Membatalkan booking melepas kursi & membatalkan invoice terbuka.
        booking.invoices.filter(status__in=['UNPAID', 'PARTIAL']).update(
            status='VOID')

    return HttpResponseRedirect(reverse('booking-view', args=[_id, ]))


@login_required(login_url='/login/')
@role_required(allowed_roles='BOOKING')
def booking_view(request, _id):
    booking = get_object_or_404(
        Booking.objects.select_related('jamaah', 'keberangkatan',
                                       'keberangkatan__paket', 'agen'),
        booking_id=_id)
    form = FormBookingView(instance=booking)
    invoices = booking.invoices.all()

    return render(request, 'home/booking_view.html', _ctx(
        request, 'booking', 'operasional', 'view', 'BOOKING',
        {'form': form, 'data': booking, 'invoices': invoices}))


# =============================================================================
# Invoice
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='INVOICE')
def invoice_index(request):
    data = Invoice.objects.select_related(
        'booking', 'booking__jamaah').order_by('-tanggal_invoice', '-invoice_id')

    return render(request, 'home/invoice_index.html',
                  _ctx(request, 'invoice', 'keuangan', 'index', 'INVOICE',
                       {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='INVOICE')
def invoice_update(request, _id):
    invoice = get_object_or_404(Invoice, invoice_id=_id)
    if request.POST:
        form = FormInvoiceUpdate(request.POST, request.FILES, instance=invoice)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('invoice-view', args=[_id, ]))
    else:
        form = FormInvoiceUpdate(instance=invoice)

    return render(request, 'home/invoice_view.html', _ctx(
        request, 'tagihan', 'keuangan', 'update', 'INVOICE',
        {'form': form, 'data': invoice, 'message': form.errors,
         'payments': invoice.payments.all().order_by('-tanggal_bayar')}))


@login_required(login_url='/login/')
@role_required(allowed_roles='INVOICE')
def invoice_view(request, _id):
    invoice = get_object_or_404(
        Invoice.objects.select_related('booking', 'booking__jamaah'),
        invoice_id=_id)
    form = FormInvoiceView(instance=invoice)
    payments = invoice.payments.all().order_by('-tanggal_bayar')

    return render(request, 'home/invoice_view.html', _ctx(
        request, 'tagihan', 'keuangan', 'view', 'INVOICE',
        {'form': form, 'data': invoice, 'payments': payments}))


# =============================================================================
# Pembayaran
# =============================================================================

@login_required(login_url='/login/')
@role_required(allowed_roles='PEMBAYARAN')
def pembayaran_index(request):
    data = Pembayaran.objects.select_related(
        'invoice', 'invoice__booking', 'invoice__booking__jamaah'
    ).order_by('-tanggal_bayar', '-pembayaran_id')

    return render(request, 'home/pembayaran_index.html', _ctx(
        request, 'pembayaran', 'keuangan', 'index', 'PEMBAYARAN', {'data': data}))


@login_required(login_url='/login/')
@role_required(allowed_roles='PEMBAYARAN')
def pembayaran_add(request):
    invoices = Invoice.objects.exclude(status='VOID').select_related(
        'booking', 'booking__jamaah').order_by('-tanggal_invoice')

    if request.POST:
        form = FormPembayaran(request.POST, request.FILES)
        if form.is_valid():
            pembayaran = form.save(commit=False)
            pembayaran.nomor_kwitansi = _next_number(
                'KW', Pembayaran, 'nomor_kwitansi', pembayaran.tanggal_bayar)
            pembayaran.status = 'PENDING'
            pembayaran.save()
            return HttpResponseRedirect(reverse('pembayaran-view', args=[pembayaran.pembayaran_id, ]))
        else:
            return render(request, 'home/pembayaran_add.html', _ctx(
                request, 'pembayaran', 'keuangan', 'add', 'PEMBAYARAN',
                {'form': form, 'invoices': invoices, 'message': form.errors}))
    else:
        form = FormPembayaran(initial={'tanggal_bayar': timezone.now().date()})
        return render(request, 'home/pembayaran_add.html', _ctx(
            request, 'pembayaran', 'keuangan', 'add', 'PEMBAYARAN',
            {'form': form, 'invoices': invoices}))


@login_required(login_url='/login/')
@role_required(allowed_roles='PEMBAYARAN')
@edit_required('PEMBAYARAN')
def pembayaran_verify(request, _id):
    pembayaran = get_object_or_404(Pembayaran, pembayaran_id=_id)
    if pembayaran.status == 'PENDING':
        pembayaran.status = 'VERIFIED'
        pembayaran.verified_by = request.user.user_id
        pembayaran.verified_at = timezone.now()
        pembayaran.save()
        _refresh_invoice_status(pembayaran.invoice)

    return HttpResponseRedirect(reverse('pembayaran-view', args=[_id, ]))


@login_required(login_url='/login/')
@role_required(allowed_roles='PEMBAYARAN')
@edit_required('PEMBAYARAN')
def pembayaran_reject(request, _id):
    pembayaran = get_object_or_404(Pembayaran, pembayaran_id=_id)
    if pembayaran.status == 'PENDING':
        pembayaran.status = 'REJECTED'
        pembayaran.verified_by = request.user.user_id
        pembayaran.verified_at = timezone.now()
        pembayaran.save()

    return HttpResponseRedirect(reverse('pembayaran-view', args=[_id, ]))


@login_required(login_url='/login/')
@role_required(allowed_roles='PEMBAYARAN')
def pembayaran_view(request, _id):
    pembayaran = get_object_or_404(
        Pembayaran.objects.select_related(
            'invoice', 'invoice__booking', 'invoice__booking__jamaah'),
        pembayaran_id=_id)
    form = FormPembayaran(instance=pembayaran)

    return render(request, 'home/pembayaran_view.html', _ctx(
        request, 'pembayaran', 'keuangan', 'view', 'PEMBAYARAN',
        {'form': form, 'data': pembayaran}))


def _refresh_invoice_status(invoice):
    """Sinkronkan status invoice dengan total pembayaran terverifikasi."""
    if invoice.status == 'VOID':
        return
    if invoice.total_terbayar >= invoice.total > 0:
        invoice.status = 'PAID'
    elif invoice.total_terbayar > 0:
        invoice.status = 'PARTIAL'
    else:
        invoice.status = 'UNPAID'
    invoice.save()
