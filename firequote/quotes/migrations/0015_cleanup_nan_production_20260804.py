from django.db import migrations
from django.db.models import Q


def clean_nan_production(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    Client = apps.get_model("quotes", "Client")

    # Elimina exclusivamente cotizaciones provenientes
    # de filas vacías del Excel.
    Quote.objects.filter(
        project_name__iexact="nan"
    ).delete()

    # Limpia campos nan de clientes relacionados con
    # cotizaciones válidas.
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

    # Elimina clientes completamente vacíos que no tengan
    # ninguna cotización asociada.
    Client.objects.filter(
        full_name="",
        company="",
        quotes__isnull=True,
    ).delete()

    # También elimina clientes nan que hayan quedado huérfanos.
    Client.objects.filter(
        Q(full_name__iexact="nan") |
        Q(company__iexact="nan"),
        quotes__isnull=True,
    ).delete()


def reverse_cleanup(apps, schema_editor):
    # Los datos basura eliminados no se reconstruyen.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0014_cleanup_nan_records'),
    ]

    operations = [
        migrations.RunPython(
            clean_nan_production,
            reverse_cleanup,
        ),
    ]