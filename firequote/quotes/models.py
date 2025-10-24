from django.db import models

# quotes/models.py
from django.db import models
from django.contrib.postgres.fields import JSONField

TITLE_CHOICES = [
    ('ingeniero', 'Ingeniero(a)'),
    ('arquitecto', 'Arquitecto(a)'),
    ('senior', 'Señor(a)'),
]

TIME_UNIT_CHOICES = [
    ('days', 'Días'),
    ('weeks', 'Semanas'),
    ('months', 'Meses'),
]

BUILDING_TYPE = [
    ('residential', 'Residencial'),
    ('commercial', 'Comercial'),
]

class Client(models.Model):
    title = models.CharField(max_length=20, choices=TITLE_CHOICES, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=200, blank=True)
    company = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} — {self.company}"

class Norm(models.Model):
    SERVICE_CHOICES = [
        ('detection', 'Detección de incendios'),
        ('protection', 'Protección contra incendios'),
        ('human_safety', 'Seguridad humana'),
    ]

    code = models.CharField(max_length=50, unique=True)  # e.g., 'NFPA 13'
    description = models.TextField(blank=True)
    services = models.JSONField(default=list, blank=True)  # lista de servicios donde aplica
    default_selected = models.BooleanField(default=False)

    def __str__(self):
        return self.code

class TemplateDoc(models.Model):
    name = models.CharField(max_length=200)  # e.g., 'protection_autocad.docx'
    file = models.FileField(upload_to='templates_docs/')
    services_tag = models.CharField(max_length=100)  # e.g., 'protection|detection'
    formats_tag = models.CharField(max_length=50)    # e.g., 'autocad', 'revit', 'both'

    def __str__(self):
        return self.name

from django.db import models

class Quote(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='quotes')
    project_name = models.CharField(max_length=250)
    is_detection = models.BooleanField(default=False)
    is_protection = models.BooleanField(default=False)
    is_human_safety = models.BooleanField(default=False)
    deliver_autocad = models.BooleanField(default=False)
    deliver_revit = models.BooleanField(default=False)
    building_type = models.CharField(max_length=20, choices=BUILDING_TYPE, blank=True)
    area_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Manual items (optional)
    manual_requirements = models.TextField(blank=True)
    manual_items_sh = models.TextField(blank=True)
    manual_items_detection = models.TextField(blank=True)
    manual_items_protection = models.TextField(blank=True)

    # Payment schedule
    payment_advance = models.DecimalField(max_digits=5, decimal_places=2, default=40.00)
    payment_first_version = models.DecimalField(max_digits=5, decimal_places=2, default=40.00)
    payment_final = models.DecimalField(max_digits=5, decimal_places=2, default=20.00)

    # Delivery time
    delivery_time_value = models.IntegerField(null=True, blank=True)
    delivery_time_unit = models.CharField(max_length=10, choices=TIME_UNIT_CHOICES, blank=True)

    # Valores de los servicios
    value_protection = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    value_detection = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    value_human_safety = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Plantilla y doc generado
    template_doc = models.ForeignKey(TemplateDoc, on_delete=models.SET_NULL, null=True, blank=True)
    generated_doc = models.FileField(upload_to='generated_quotes/', null=True, blank=True)

    # Nuevo campo opcional para mantener compatibilidad con views.py
    service_tag = models.CharField(max_length=50, blank=True, null=True)  # <-- agregado

    # Fecha de creación
    created_at = models.DateTimeField(auto_now_add=True)  # puedes usar en lugar de quote_date

    norms = models.ManyToManyField(Norm, blank=True)

    def __str__(self):
        return f"{self.client.full_name} - {self.project_name}"
