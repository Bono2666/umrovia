from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from crum import get_current_user


class User(AbstractUser):
    is_active = models.BooleanField(default=True)
    user_id = models.CharField(max_length=50, primary_key=True)
    username = models.CharField(max_length=50)
    position = models.ForeignKey(
        'Position', on_delete=models.CASCADE, null=True)
    signature = models.ImageField(upload_to='signature/', null=True)
    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True)
    update_by = models.CharField(max_length=50, null=True)

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(User, self).save(*args, **kwargs)

    USERNAME_FIELD = 'user_id'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username


class Position(models.Model):
    position_id = models.CharField(
        max_length=3, primary_key=True, help_text='Max 3 digits Position shortname.')
    position_name = models.CharField(max_length=50)
    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True)
    update_by = models.CharField(max_length=50, null=True)

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        self.position_id = self.position_id.upper()
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(Position, self).save(*args, **kwargs)

    def __str__(self):
        return self.position_name


class Menu(models.Model):
    menu_id = models.CharField(max_length=50, primary_key=True)
    menu_name = models.CharField(max_length=50)
    menu_remark = models.CharField(max_length=200, null=True, blank=True)
    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True)
    update_by = models.CharField(max_length=50, null=True)

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        self.menu_id = self.menu_id.upper()
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(Menu, self).save(*args, **kwargs)

    def __str__(self):
        return self.menu_name


class Auth(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    add = models.BooleanField(default=False)
    edit = models.BooleanField(default=False)
    delete = models.BooleanField(default=False)
    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True)
    update_by = models.CharField(max_length=50, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'menu'], name='unique_user_menu')
        ]

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(Auth, self).save(*args, **kwargs)

    def __str__(self):
        return self.menu.menu_name


class UploadLog(models.Model):
    document = models.CharField(max_length=50)
    document_id = models.CharField(max_length=50)
    description = models.CharField(max_length=200)
    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True)
    update_by = models.CharField(max_length=50, null=True)

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(UploadLog, self).save(*args, **kwargs)


class AuditModel(models.Model):
    """Base model untuk kolom audit yang dipakai seluruh model bisnis Umrovia."""

    entry_date = models.DateTimeField(null=True)
    entry_by = models.CharField(max_length=50, null=True)
    update_date = models.DateTimeField(null=True, blank=True)
    update_by = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        user_id = user.user_id if user else None
        if not self.entry_date:
            self.entry_date = timezone.now()
            self.entry_by = user_id
        self.update_date = timezone.now()
        self.update_by = user_id
        super(AuditModel, self).save(*args, **kwargs)


class Agen(AuditModel):
    STATUS_CHOICES = [('AKTIF', 'Aktif'), ('NONAKTIF', 'Non Aktif')]

    agen_id = models.CharField(
        max_length=10, primary_key=True, help_text='Kode agen, contoh: AG001.')
    nama_agen = models.CharField(max_length=100)
    telepon = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    alamat = models.CharField(max_length=200, null=True, blank=True)
    komisi_persen = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name='Komisi (%)')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='AKTIF')

    def save(self, *args, **kwargs):
        self.agen_id = self.agen_id.strip().upper()
        self.nama_agen = self.nama_agen.strip()
        super(Agen, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.agen_id} - {self.nama_agen}'


class Paket(AuditModel):
    JENIS_CHOICES = [
        ('UMROH', 'Umroh'),
        ('HAJI', 'Haji'),
        ('ZIARAH', 'Ziarah'),
    ]
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Aktif'),
        ('INACTIVE', 'Non Aktif'),
        ('ARCHIVED', 'Diarsipkan'),
    ]

    paket_id = models.CharField(
        max_length=10, primary_key=True, help_text='Kode paket, contoh: PKU001.')
    nama_paket = models.CharField(max_length=100)
    jenis = models.CharField(
        max_length=10, choices=JENIS_CHOICES, default='UMROH')
    deskripsi = models.TextField(blank=True, default='')
    durasi_hari = models.PositiveIntegerField(default=0)
    harga = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name='Harga Dasar (Rp)')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='DRAFT')

    class Meta:
        verbose_name_plural = 'Paket'

    def save(self, *args, **kwargs):
        self.paket_id = self.paket_id.strip().upper()
        self.nama_paket = self.nama_paket.strip()
        super(Paket, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.paket_id} - {self.nama_paket}'


class Keberangkatan(AuditModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('OPEN', 'Open'),
        ('FULL', 'Penuh'),
        ('CLOSED', 'Ditutup'),
        ('PREPARATION', 'Persiapan'),
        ('DEPARTED', 'Berangkat'),
        ('COMPLETED', 'Selesai'),
        ('CANCELLED', 'Dibatalkan'),
    ]

    keberangkatan_id = models.BigAutoField(primary_key=True)
    kode_keberangkatan = models.CharField(max_length=20, unique=True)
    paket = models.ForeignKey(
        'Paket', on_delete=models.PROTECT, related_name='keberangkatans')
    tanggal_berangkat = models.DateField()
    tanggal_kembali = models.DateField(null=True, blank=True)
    kota_asal = models.CharField(max_length=100)
    kapasitas = models.PositiveIntegerField(default=0)
    kuota_blokir = models.PositiveIntegerField(
        default=0, verbose_name='Kuota Diblokir')
    batas_pendaftaran = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    catatan = models.TextField(blank=True, default='')

    @property
    def kursi_terpakai(self):
        return self.bookings.filter(
            status__in=Booking.SEAT_CONSUMING_STATUSES).count()

    @property
    def kursi_tersedia(self):
        available = self.kapasitas - self.kuota_blokir - self.kursi_terpakai
        return available if available > 0 else 0

    def save(self, *args, **kwargs):
        self.kode_keberangkatan = self.kode_keberangkatan.strip().upper()
        self.kota_asal = self.kota_asal.strip()
        super(Keberangkatan, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.kode_keberangkatan} - {self.paket.nama_paket}'


class Jamaah(AuditModel):
    GENDER_CHOICES = [('L', 'Laki-Laki'), ('P', 'Perempuan')]

    jamaah_id = models.BigAutoField(primary_key=True)
    kode_jamaah = models.CharField(max_length=15, unique=True)
    nama = models.CharField(max_length=100)
    nik = models.CharField(max_length=20, null=True, blank=True)
    jenis_kelamin = models.CharField(
        max_length=1, choices=GENDER_CHOICES, default='L')
    tempat_lahir = models.CharField(max_length=50, null=True, blank=True)
    tanggal_lahir = models.DateField(null=True, blank=True)
    alamat = models.CharField(max_length=200, null=True, blank=True)
    telepon = models.CharField(max_length=20, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    nomor_paspor = models.CharField(max_length=30, null=True, blank=True)
    paspor_terbit = models.DateField(null=True, blank=True)
    paspor_kedaluwarsa = models.DateField(null=True, blank=True)
    tempat_paspor = models.CharField(max_length=100, null=True, blank=True)
    kontak_darurat = models.CharField(max_length=100, null=True, blank=True)
    telepon_darurat = models.CharField(max_length=20, null=True, blank=True)
    catatan = models.TextField(blank=True, default='')

    def save(self, *args, **kwargs):
        self.kode_jamaah = self.kode_jamaah.strip().upper()
        self.nama = self.nama.strip()
        super(Jamaah, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.kode_jamaah} - {self.nama}'


class Booking(AuditModel):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('RESERVED', 'Dipesan'),
        ('CONFIRMED', 'Terkonfirmasi'),
        ('READY', 'Siap Berangkat'),
        ('DEPARTED', 'Berangkat'),
        ('COMPLETED', 'Selesai'),
        ('CANCELED', 'Dibatalkan'),
    ]
    # Status yang mengonsumsi kursi pada keberangkatan terkait.
    SEAT_CONSUMING_STATUSES = (
        'RESERVED', 'CONFIRMED', 'READY', 'DEPARTED')

    booking_id = models.BigAutoField(primary_key=True)
    nomor_booking = models.CharField(max_length=30, unique=True)
    tanggal_booking = models.DateField()
    keberangkatan = models.ForeignKey(
        'Keberangkatan', on_delete=models.PROTECT, related_name='bookings')
    jamaah = models.ForeignKey(
        'Jamaah', on_delete=models.PROTECT, related_name='bookings',
        verbose_name='Jamaah')
    agen = models.ForeignKey(
        'Agen', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings')
    harga = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name='Harga Satuan (Rp)')
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='RESERVED')
    catatan = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['jamaah', 'keberangkatan'],
                condition=~models.Q(status='CANCELED'),
                name='unique_active_booking_per_jamaah_departure'),
        ]

    def save(self, *args, **kwargs):
        self.nomor_booking = self.nomor_booking.strip().upper()
        super(Booking, self).save(*args, **kwargs)

    def __str__(self):
        return self.nomor_booking


class Invoice(AuditModel):
    STATUS_CHOICES = [
        ('UNPAID', 'Belum Dibayar'),
        ('PARTIAL', 'Sebagian'),
        ('PAID', 'Lunas'),
        ('VOID', 'Dibatalkan'),
    ]

    invoice_id = models.BigAutoField(primary_key=True)
    nomor_invoice = models.CharField(max_length=30, unique=True)
    booking = models.ForeignKey(
        'Booking', on_delete=models.PROTECT, related_name='invoices')
    tanggal_invoice = models.DateField()
    jatuh_tempo = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='UNPAID')
    catatan = models.TextField(blank=True, default='')

    @property
    def total_terbayar(self):
        return self.payments.filter(status='VERIFIED').aggregate(
            total=models.Sum('nominal'))['total'] or 0

    @property
    def sisa_tagihan(self):
        sisa = self.total - self.total_terbayar
        return sisa if sisa > 0 else 0

    def save(self, *args, **kwargs):
        self.nomor_invoice = self.nomor_invoice.strip().upper()
        super(Invoice, self).save(*args, **kwargs)

    def __str__(self):
        return self.nomor_invoice


class Pembayaran(AuditModel):
    METODE_CHOICES = [
        ('TUNAI', 'Tunai'),
        ('TRANSFER', 'Transfer Bank'),
        ('QRIS', 'QRIS'),
        ('LAINNYA', 'Lainnya'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Menunggu Verifikasi'),
        ('VERIFIED', 'Terverifikasi'),
        ('REJECTED', 'Ditolak'),
    ]

    pembayaran_id = models.BigAutoField(primary_key=True)
    nomor_kwitansi = models.CharField(max_length=30, unique=True)
    invoice = models.ForeignKey(
        'Invoice', on_delete=models.PROTECT, related_name='payments')
    tanggal_bayar = models.DateField()
    metode = models.CharField(
        max_length=10, choices=METODE_CHOICES, default='TRANSFER')
    nominal = models.DecimalField(max_digits=15, decimal_places=2)
    referensi = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name='No. Referensi')
    bukti_bayar = models.FileField(
        upload_to='pembayaran/', null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='PENDING')
    verified_by = models.CharField(max_length=50, null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    catatan = models.TextField(blank=True, default='')

    def save(self, *args, **kwargs):
        self.nomor_kwitansi = self.nomor_kwitansi.strip().upper()
        super(Pembayaran, self).save(*args, **kwargs)

    def __str__(self):
        return self.nomor_kwitansi
