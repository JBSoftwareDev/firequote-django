from django.db import migrations
from django.db.models import Q


def clean_nan_records(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    Client = apps.get_model("quotes", "Client")

    # Eliminar cotizaciones basura creadas por filas vacías del Excel.
    Quote.objects.filter(
        project_name__iexact="nan"
    ).delete()

    # Eliminar clientes nan que ya no tengan cotizaciones.
    Client.objects.filter(
        Q(full_name__iexact="nan") |
        Q(company__iexact="nan"),
        quotes__isnull=True,
    ).delete()

    # Limpiar campos nan de clientes que sí tengan cotizaciones válidas.
    Client.objects.filter(
        full_name__iexact="nan"
    ).update(full_name="")

    Client.objects.filter(
        company__iexact="nan"
    ).update(company="")

    Client.objects.filter(
        position__iexact="nan"
    ).update(position="")

    Client.objects.filter(
        city__iexact="nan"
    ).update(city="")

    Client.objects.filter(
        title__iexact="nan"
    ).update(title="")

    Client.objects.filter(
        email__iexact="nan"
    ).update(email=None)

    Client.objects.filter(
        phone__iexact="nan"
    ).update(phone=None)

    # Eliminar clientes completamente vacíos y sin cotizaciones.
    Client.objects.filter(
        full_name="",
        company="",
        quotes__isnull=True,
    ).delete()


def reverse_cleanup(apps, schema_editor):
    # Esta limpieza de datos no puede reconstruirse automáticamente.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0013_quote_additional_notes'),
    ]

    operations = [
        migrations.RunPython(
            clean_nan_records,
            reverse_cleanup,
        ),
    ]