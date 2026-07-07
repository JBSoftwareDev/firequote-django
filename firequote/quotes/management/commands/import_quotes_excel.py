import pandas as pd
from decimal import Decimal
import unicodedata

from django.core.management.base import BaseCommand

from quotes.models import (
    Client,
    Quote
)

def normalize_text(value):
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value


def get_name_keys(full_name):
    tokens = normalize_text(full_name).split()

    if len(tokens) < 2:
        return set()

    keys = set()

    first_name = tokens[0]

    for token in tokens[1:]:
        keys.add(f"{first_name} {token}")

    if len(tokens) >= 3:
        keys.add(f"{tokens[1]} {tokens[2]}")

    return keys

class Command(BaseCommand):

    help = "Importa clientes y cotizaciones"

    def handle(self, *args, **kwargs):

        path = "Seguimiento a cotizaciones.xlsx"

        years = [
            "2020",
            "2021",
            "2022",
            "2023",
            "2024",
            "2025",
            "2026"
        ]

        clients_created = 0
        quotes_created = 0

        Quote.objects.all().delete()
        Client.objects.all().delete()

        client_index = {}

        for sheet in years:

            try:

                raw = pd.read_excel(
                    path,
                    sheet_name=sheet,
                    header=None
                )

            except:
                continue

            header = None

            for i, row in raw.iterrows():

                values = row.astype(str)

                if (
                    values.str.contains(
                        "Cliente",
                        case=False,
                        na=False
                    ).any()
                ):

                    header = i
                    break

            if header is None:
                continue

            df = raw.iloc[header:]

            df.columns = df.iloc[0]

            df = df.iloc[1:]

            df = df.rename(
                columns={
                    "Cliente": "company",
                    "Persona Encargada": "full_name",
                    "Cargo": "position",
                    "Correo": "email",
                    "Telefono": "phone",
                    "Descripción de la cotización": "project_name",
                    "Valor sin IVA": "total_value",
                    "Fecha de cotización": "created_at",
                }
            )

            for _, row in df.iterrows():

                company = str(
                    row.get(
                        "company",
                        ""
                    )
                ).strip()

                full_name = str(
                    row.get(
                        "full_name",
                        ""
                    )
                ).strip()

                email = str(
                    row.get(
                        "email",
                        ""
                    )
                ).strip()

                phone = str(
                    row.get(
                        "phone",
                        ""
                    )
                ).strip()

                position = str(
                    row.get(
                        "position",
                        ""
                    )
                ).strip()

                if position.lower() == "nan":
                    position = ""

                if (
                    not company
                    and
                    not full_name
                ):
                    continue

                name_keys = get_name_keys(full_name)

                client = None

                for key in name_keys:
                    if key in client_index:
                        client = client_index[key]
                        break

                if not client:
                    client = Client.objects.create(
                        company=company,
                        full_name=full_name,
                        email=email,
                        phone=phone,
                        title="",
                        position=position,
                        city=""
                    )

                    clients_created += 1

                else:
                    if full_name:
                        client.full_name = full_name

                    if company:
                        client.company = company

                    if email:
                        client.email = email

                    if phone:
                        client.phone = phone

                    if position:
                        client.position = position

                    client.save()

                for key in name_keys:
                    client_index[key] = client

                value = row.get("total_value")

                try:
                    if pd.isna(value):
                        value = Decimal("0")

                    elif isinstance(value, (int, float)):
                        value = Decimal(str(value)).quantize(Decimal("0.01"))

                    else:
                        value = str(value).strip()

                        value = value.replace("$", "")
                        value = value.replace("COP", "")
                        value = value.replace(" ", "")

                        # Caso colombiano: 1.234.567,89
                        if "," in value:
                            value = value.replace(".", "")
                            value = value.replace(",", ".")

                        # Caso Excel/texto: 1234567.89
                        value = Decimal(value).quantize(Decimal("0.01"))

                except:
                    value = Decimal("0")

                # Protección contra valores absurdos por celdas mal leídas
                if value >= Decimal("1000000000000"):
                    value = Decimal("0")

                Quote.objects.create(

                    client=client,

                    project_name=
                    str(
                        row.get(
                            "project_name",
                            ""
                        )
                    )[:250],

                    total_value=value,

                    created_at=
                    row.get(
                        "created_at"
                    ),

                    building_type="",

                    area_sqm=None,

                    is_detection=False,

                    is_protection=False,

                    is_human_safety=False,

                    deliver_autocad=False,

                    deliver_revit=False
                )

                quotes_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"""
Clientes creados:
{clients_created}

Cotizaciones creadas:
{quotes_created}
"""
            )
        )