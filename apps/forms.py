from django import forms
from django.forms import ModelForm
from apps.models import *
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm, UserCreationForm


class FormUser(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super(FormUser, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['user_id'].label = 'User ID'
        self.fields['username'].label = 'Nama User'
        self.fields['email'].label = 'Email'
        self.fields['position'].label = 'Posisi'
        self.fields['signature'].label = 'Tanda Tangan'
        self.fields['signature'].required = False
        self.fields['password1'].label = 'Password'
        self.fields['password2'].label = 'Konfirmasi Password'
        self.fields['user_id'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['username'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm'})
        self.fields['password1'].widget = forms.PasswordInput(
            {'class': 'form-control-sm'})
        self.fields['password2'].widget = forms.PasswordInput(
            {'class': 'form-control-sm'})

    class Meta:
        model = User
        exclude = ['date_joined', 'password', 'is_active', 'is_staff',
                   'is_superuser', 'entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'signature': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
        }


class FormUserView(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormUserView, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['username'].label = 'Nama User'
        self.fields['email'].label = 'Email'
        self.fields['position'].label = 'Posisi'
        self.fields['username'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})

    class Meta:
        model = User
        fields = ['user_id', 'username', 'email', 'position', 'signature']

        widgets = {
            'position': forms.Select(attrs={'class': 'form-control form-select-sm', 'disabled': 'disabled'}),
            'signature': forms.FileInput(attrs={'class': 'form-control form-control-sm', 'disabled': 'disabled'}),
        }


class FormUserUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormUserUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['username'].label = 'Nama User'
        self.fields['email'].label = 'Email'
        self.fields['position'].label = 'Posisi'
        self.fields['username'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm'})
        self.fields['signature'].required = False

    class Meta:
        model = User
        exclude = ['user_id', 'password', 'date_joined',
                   'is_active', 'is_staff', 'is_superuser', 'entry_date', 'entry_by', 'update_date', 'update_by']

        widgets = {
            'position': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'signature': forms.FileInput(attrs={'class': 'form-control form-control-sm'}),
        }


class FormChangePassword(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super(FormChangePassword, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['old_password'].label = 'Password Lama'
        self.fields['new_password1'].label = 'Password Baru'
        self.fields['new_password2'].label = 'Konfirmasi Password Baru'
        self.fields['old_password'].widget = forms.PasswordInput(
            {'class': 'form-control-sm z-index-2'})
        self.fields['new_password1'].widget = forms.PasswordInput(
            {'class': 'form-control-sm z-index-2'})
        self.fields['new_password2'].widget = forms.PasswordInput(
            {'class': 'form-control-sm z-index-2'})


class FormSetPassword(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super(FormSetPassword, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['new_password1'].label = 'Password Baru'
        self.fields['new_password2'].label = 'Konfirmasi Password Baru'
        self.fields['new_password1'].widget = forms.PasswordInput(
            {'class': 'form-control-sm'})
        self.fields['new_password2'].widget = forms.PasswordInput(
            {'class': 'form-control-sm'})


class FormPosition(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPosition, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['position_id'].label = 'ID Posisi'
        self.fields['position_name'].label = 'Nama Posisi'
        self.fields['position_id'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'placeholder': 'XXX'})
        self.fields['position_name'].widget = forms.TextInput(
            {'class': 'form-control-sm'})

    class Meta:
        model = Position
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']


class FormPositionUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPositionUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['position_name'].label = 'Nama Posisi'
        self.fields['position_name'].widget = forms.TextInput(
            {'class': 'form-control-sm'})

    class Meta:
        model = Position
        exclude = ['position_id', 'entry_date',
                   'entry_by', 'update_date', 'update_by']


class FormPositionView(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPositionView, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['position_name'].label = 'Nama Posisi'
        self.fields['position_name'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})

    class Meta:
        model = Position
        fields = ['position_id', 'position_name']


class FormMenu(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormMenu, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['menu_id'].label = 'ID Menu'
        self.fields['menu_name'].label = 'Nama Menu'
        self.fields['menu_remark'].label = 'Deskripsi'
        self.fields['menu_id'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase'})
        self.fields['menu_name'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['menu_remark'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Menu
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']


class FormMenuUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormMenuUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['menu_name'].label = 'Nama Menu'
        self.fields['menu_remark'].label = 'Deskripsi'
        self.fields['menu_name'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['menu_remark'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Menu
        exclude = ['menu_id', 'entry_date',
                   'entry_by', 'update_date', 'update_by']


class FormMenuView(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormMenuView, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['menu_name'].label = 'Nama Menu'
        self.fields['menu_remark'].label = 'Deskripsi'
        self.fields['menu_name'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['menu_remark'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3, 'readonly': 'readonly'})

    class Meta:
        model = Menu
        fields = ['menu_id', 'menu_name', 'menu_remark']


class FormAuthUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormAuthUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['add'].widget = forms.CheckboxInput(
            {'class': 'border mt-1'})
        self.fields['edit'].widget = forms.CheckboxInput(
            {'class': 'border mt-1'})
        self.fields['delete'].widget = forms.CheckboxInput(
            {'class': 'border mt-1'})

    class Meta:
        model = Auth
        exclude = ['user', 'entry_date',
                   'entry_by', 'update_date', 'update_by']


class FormAgen(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormAgen, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['agen_id'].label = 'Kode Agen'
        self.fields['nama_agen'].label = 'Nama Agen'
        self.fields['telepon'].label = 'Telepon'
        self.fields['email'].label = 'Email'
        self.fields['alamat'].label = 'Alamat'
        self.fields['komisi_persen'].label = 'Komisi (%)'
        self.fields['status'].label = 'Status'
        self.fields['agen_id'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'placeholder': 'AG001'})
        self.fields['nama_agen'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['telepon'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm'})
        self.fields['alamat'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['komisi_persen'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '0.01', 'min': '0'})

    class Meta:
        model = Agen
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormAgenUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormAgenUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['nama_agen'].label = 'Nama Agen'
        self.fields['telepon'].label = 'Telepon'
        self.fields['email'].label = 'Email'
        self.fields['alamat'].label = 'Alamat'
        self.fields['komisi_persen'].label = 'Komisi (%)'
        self.fields['status'].label = 'Status'
        self.fields['nama_agen'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['telepon'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm'})
        self.fields['alamat'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['komisi_persen'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '0.01', 'min': '0'})

    class Meta:
        model = Agen
        exclude = ['agen_id', 'entry_date',
                   'entry_by', 'update_date', 'update_by']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormAgenView(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormAgenView, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['nama_agen'].label = 'Nama Agen'
        self.fields['telepon'].label = 'Telepon'
        self.fields['email'].label = 'Email'
        self.fields['alamat'].label = 'Alamat'
        self.fields['komisi_persen'].label = 'Komisi (%)'
        self.fields['status'].label = 'Status'
        for field in self.fields.values():
            field.widget.attrs['readonly'] = 'readonly'

    class Meta:
        model = Agen
        fields = ['agen_id', 'nama_agen', 'telepon', 'email',
                  'alamat', 'komisi_persen', 'status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control form-select-sm', 'disabled': 'disabled'}),
        }


class FormPaket(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPaket, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['paket_id'].label = 'Kode Paket'
        self.fields['nama_paket'].label = 'Nama Paket'
        self.fields['jenis'].label = 'Jenis Layanan'
        self.fields['deskripsi'].label = 'Deskripsi'
        self.fields['durasi_hari'].label = 'Durasi (Hari)'
        self.fields['harga'].label = 'Harga Dasar (Rp)'
        self.fields['status'].label = 'Status'
        self.fields['paket_id'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'placeholder': 'PKU001'})
        self.fields['nama_paket'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['deskripsi'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})
        self.fields['durasi_hari'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'min': '0'})
        self.fields['harga'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '1', 'min': '0'})

    class Meta:
        model = Paket
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'jenis': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormPaketUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPaketUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['nama_paket'].label = 'Nama Paket'
        self.fields['jenis'].label = 'Jenis Layanan'
        self.fields['deskripsi'].label = 'Deskripsi'
        self.fields['durasi_hari'].label = 'Durasi (Hari)'
        self.fields['harga'].label = 'Harga Dasar (Rp)'
        self.fields['status'].label = 'Status'
        self.fields['nama_paket'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['deskripsi'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})
        self.fields['durasi_hari'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'min': '0'})
        self.fields['harga'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '1', 'min': '0'})

    class Meta:
        model = Paket
        exclude = ['paket_id', 'entry_date',
                   'entry_by', 'update_date', 'update_by']
        widgets = {
            'jenis': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormPaketView(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPaketView, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['nama_paket'].label = 'Nama Paket'
        self.fields['jenis'].label = 'Jenis Layanan'
        self.fields['deskripsi'].label = 'Deskripsi'
        self.fields['durasi_hari'].label = 'Durasi (Hari)'
        self.fields['harga'].label = 'Harga Dasar (Rp)'
        self.fields['status'].label = 'Status'
        self.fields['nama_paket'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['deskripsi'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3, 'readonly': 'readonly'})
        self.fields['durasi_hari'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['harga'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})

    class Meta:
        model = Paket
        fields = ['paket_id', 'nama_paket', 'jenis', 'deskripsi',
                  'durasi_hari', 'harga', 'status']
        widgets = {
            'jenis': forms.Select(attrs={'class': 'form-control form-select-sm', 'disabled': 'disabled'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm', 'disabled': 'disabled'}),
        }


class FormKeberangkatan(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormKeberangkatan, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['kode_keberangkatan'].label = 'Kode Keberangkatan'
        self.fields['paket'].label = 'Paket'
        self.fields['tanggal_berangkat'].label = 'Tanggal Berangkat'
        self.fields['tanggal_kembali'].label = 'Tanggal Kembali'
        self.fields['kota_asal'].label = 'Kota Asal'
        self.fields['kapasitas'].label = 'Kapasitas Kursi'
        self.fields['kuota_blokir'].label = 'Kuota Diblokir'
        self.fields['batas_pendaftaran'].label = 'Batas Pendaftaran'
        self.fields['status'].label = 'Status'
        self.fields['catatan'].label = 'Catatan'
        self.fields['kode_keberangkatan'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'placeholder': 'UMR-2026-01'})
        self.fields['kota_asal'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['kapasitas'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'min': '0'})
        self.fields['kuota_blokir'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'min': '0'})
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Keberangkatan
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'paket': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'tanggal_berangkat': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'tanggal_kembali': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'batas_pendaftaran': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormKeberangkatanUpdate(FormKeberangkatan):
    def __init__(self, *args, **kwargs):
        super(FormKeberangkatanUpdate, self).__init__(*args, **kwargs)
        self.fields['kode_keberangkatan'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'readonly': 'readonly'})


class FormKeberangkatanView(FormKeberangkatan):
    def __init__(self, *args, **kwargs):
        super(FormKeberangkatanView, self).__init__(*args, **kwargs)
        self.fields['kode_keberangkatan'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['kota_asal'].widget = forms.TextInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['kapasitas'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['kuota_blokir'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'readonly': 'readonly'})
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3, 'readonly': 'readonly'})
        self.fields['paket'].widget.attrs['disabled'] = 'disabled'
        self.fields['status'].widget.attrs['disabled'] = 'disabled'


class FormJamaah(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormJamaah, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['kode_jamaah'].label = 'Kode Jamaah'
        self.fields['nama'].label = 'Nama Lengkap'
        self.fields['nik'].label = 'NIK'
        self.fields['jenis_kelamin'].label = 'Jenis Kelamin'
        self.fields['tempat_lahir'].label = 'Tempat Lahir'
        self.fields['tanggal_lahir'].label = 'Tanggal Lahir'
        self.fields['alamat'].label = 'Alamat'
        self.fields['telepon'].label = 'Telepon'
        self.fields['email'].label = 'Email'
        self.fields['nomor_paspor'].label = 'Nomor Paspor'
        self.fields['paspor_terbit'].label = 'Paspor Terbit'
        self.fields['paspor_kedaluwarsa'].label = 'Paspor Kedaluwarsa'
        self.fields['tempat_paspor'].label = 'Tempat Terbit Paspor'
        self.fields['kontak_darurat'].label = 'Kontak Darurat'
        self.fields['telepon_darurat'].label = 'Telepon Darurat'
        self.fields['catatan'].label = 'Catatan'
        self.fields['kode_jamaah'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'placeholder': 'JM0001'})
        self.fields['nama'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['nik'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['tempat_lahir'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['alamat'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['telepon'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['email'].widget = forms.EmailInput(
            {'class': 'form-control-sm'})
        self.fields['nomor_paspor'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['tempat_paspor'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['kontak_darurat'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['telepon_darurat'].widget = forms.TextInput(
            {'class': 'form-control-sm'})
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Jamaah
        exclude = ['entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'tanggal_lahir': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'paspor_terbit': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'paspor_kedaluwarsa': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
        }


class FormJamaahUpdate(FormJamaah):
    def __init__(self, *args, **kwargs):
        super(FormJamaahUpdate, self).__init__(*args, **kwargs)
        self.fields['kode_jamaah'].widget = forms.TextInput(
            {'class': 'form-control-sm text-uppercase', 'readonly': 'readonly'})


class FormJamaahView(FormJamaah):
    def __init__(self, *args, **kwargs):
        super(FormJamaahView, self).__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'jenis_kelamin':
                field.widget.attrs['disabled'] = 'disabled'
            else:
                field.widget.attrs['readonly'] = 'readonly'
        self.fields['catatan'].widget.attrs.pop('type', None)


class FormBooking(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormBooking, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['tanggal_booking'].label = 'Tanggal Booking'
        self.fields['keberangkatan'].label = 'Keberangkatan'
        self.fields['jamaah'].label = 'Jamaah'
        self.fields['agen'].label = 'Agen'
        self.fields['harga'].label = 'Harga Satuan (Rp)'
        self.fields['status'].label = 'Status'
        self.fields['catatan'].label = 'Catatan'
        self.fields['agen'].required = False
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})
        self.fields['harga'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '1', 'min': '0'})

    class Meta:
        model = Booking
        exclude = ['nomor_booking', 'entry_date',
                   'entry_by', 'update_date', 'update_by']
        widgets = {
            'tanggal_booking': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'keberangkatan': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'jamaah': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'agen': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormBookingUpdate(FormBooking):
    def __init__(self, *args, **kwargs):
        super(FormBookingUpdate, self).__init__(*args, **kwargs)
        # Keberangkatan dan jamaah tidak boleh berubah setelah booking dibuat.
        self.fields['keberangkatan'].widget.attrs['disabled'] = 'disabled'
        self.fields['jamaah'].widget.attrs['disabled'] = 'disabled'


class FormBookingView(FormBooking):
    def __init__(self, *args, **kwargs):
        super(FormBookingView, self).__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in ('keberangkatan', 'jamaah', 'agen', 'status'):
                field.widget.attrs['disabled'] = 'disabled'
            else:
                field.widget.attrs['readonly'] = 'readonly'


class FormInvoiceUpdate(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormInvoiceUpdate, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['tanggal_invoice'].label = 'Tanggal Invoice'
        self.fields['jatuh_tempo'].label = 'Jatuh Tempo'
        self.fields['total'].label = 'Total (Rp)'
        self.fields['status'].label = 'Status'
        self.fields['catatan'].label = 'Catatan'
        self.fields['total'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '1', 'min': '0'})
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Invoice
        exclude = ['nomor_invoice', 'booking', 'entry_date',
                   'entry_by', 'update_date', 'update_by']
        widgets = {
            'tanggal_invoice': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'jatuh_tempo': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-control form-select-sm'}),
        }


class FormInvoiceView(FormInvoiceUpdate):
    def __init__(self, *args, **kwargs):
        super(FormInvoiceView, self).__init__(*args, **kwargs)
        self.fields['status'].widget.attrs['disabled'] = 'disabled'
        for name in ('tanggal_invoice', 'jatuh_tempo', 'total', 'catatan'):
            self.fields[name].widget.attrs['readonly'] = 'readonly'


class FormPembayaran(ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormPembayaran, self).__init__(*args, **kwargs)
        self.label_suffix = ''
        self.fields['invoice'].label = 'Invoice'
        self.fields['tanggal_bayar'].label = 'Tanggal Bayar'
        self.fields['metode'].label = 'Metode'
        self.fields['nominal'].label = 'Nominal (Rp)'
        self.fields['referensi'].label = 'No. Referensi'
        self.fields['bukti_bayar'].label = 'Bukti Bayar'
        self.fields['catatan'].label = 'Catatan'
        self.fields['bukti_bayar'].required = False
        self.fields['referensi'].required = False
        self.fields['nominal'].widget = forms.NumberInput(
            {'class': 'form-control-sm', 'step': '1', 'min': '1'})
        self.fields['catatan'].widget = forms.Textarea(
            {'class': 'form-control-sm', 'rows': 3})

    class Meta:
        model = Pembayaran
        exclude = ['nomor_kwitansi', 'status', 'verified_by', 'verified_at',
                   'entry_date', 'entry_by', 'update_date', 'update_by']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'tanggal_bayar': forms.DateInput(
                {'class': 'form-control-sm', 'type': 'date'}),
            'metode': forms.Select(attrs={'class': 'form-control form-select-sm'}),
            'bukti_bayar': forms.FileInput(
                {'class': 'form-control form-control-sm'}),
        }
