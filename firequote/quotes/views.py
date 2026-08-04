from .services.quote_service import (
    format_currency,
    parse_items,
    build_total_text,
    build_additional_notes,
    build_payment_schedule,
    get_template_filename,
    build_output_filename,
    get_next_quote_number,
)
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Q
import locale
import os
from .models import Quote, Client, Norm, TemplateDoc, QuoteCounter
from django.conf import settings
from docxtpl import Listing, RichText
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .services.excel_report_service import (
    generate_quotes_excel_report,
)

"""
quotes/views.py
---------------
Handles quote creation, editing, and document generation (.docx)
for the FireQuote Django web application.
"""

import zlib

from django.core import serializers
from django.http import StreamingHttpResponse

import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone

logger = logging.getLogger(__name__)

# View: displays and handles the quote creation form
def quote_form(request):
    clients = Client.objects.all()  # populate dropdown with existing clients

    if request.method == "POST":
        client_id = request.POST.get("existing_client")
        project_name = request.POST.get("project_name")
        service_tag = request.POST.get("service_tag") or "default"
        delivery_time_value = request.POST.get("delivery_time_value") or 0
        delivery_time_unit = request.POST.get("delivery_time_unit") or "days"

        # If no existing client selected, create a new one if data provided
        if not client_id:
            new_name = request.POST.get("new_client_name")
            new_company = request.POST.get("new_client_company")
            if new_name and new_company:
                client = Client.objects.create(
                    full_name=new_name,
                    company=new_company,
                    email=request.POST.get("new_client_email", ""),
                    phone=request.POST.get("new_client_phone", ""),
                    title=request.POST.get("new_client_title", ""),
                    position=request.POST.get("new_client_position", ""),
                    city=request.POST.get("new_client_city", "")
                )
                client_id = client.id

        # Validate required fields
        if not all([client_id, project_name]):
            messages.error(request, "Por favor completa todos los campos obligatorios.")
            return redirect("quote_form")

        client = get_object_or_404(Client, id=client_id)

        client.title = request.POST.get("new_client_title", "") or client.title
        client.full_name = request.POST.get("new_client_name", "") or client.full_name
        client.company = request.POST.get("new_client_company", "") or client.company
        client.email = request.POST.get("new_client_email", "") or client.email
        client.phone = request.POST.get("new_client_phone", "") or client.phone
        client.position = request.POST.get("new_client_position", "") or client.position
        client.city = request.POST.get("new_client_city", "") or client.city

        client.save()

        quote_year, quote_number = get_next_quote_number()

        # Create the quote record with service and format options
        quote = Quote.objects.create(
            client=client,
            project_name=project_name,
            service_tag=service_tag,
            delivery_time_value=delivery_time_value,
            delivery_time_unit=delivery_time_unit,

            is_detection=('is_detection' in request.POST),
            is_protection=('is_protection' in request.POST),
            is_human_safety=('is_human_safety' in request.POST),
            deliver_autocad=('deliver_autocad' in request.POST),
            deliver_revit=('deliver_revit' in request.POST),

            quote_year=quote_year,
            quote_number=quote_number,
        )

        messages.success(request, "Cotización creada correctamente.")
        return redirect("quote_details", quote_id=quote.id)

    # On GET: render the empty quote creation form
    preselected_client_id = request.GET.get("client_id")

    return render(
        request,
        "quotes/quote_form.html",
        {
            "clients": clients,
            "preselected_client_id": preselected_client_id,
        }
    )

def money_to_decimal(value):
    """
    Converts values such as:
    1500000
    $1.500.000
    1,500,000
    into Decimal.
    """
    try:
        clean_value = (
            str(value or "0")
            .replace("$", "")
            .replace(".", "")
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )
        return Decimal(clean_value or "0")
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("0")


def save_quote_details(quote, request):
    """
    Updates a quote using the submitted detail form.
    It does not generate or store a Word document.
    """

    quote.project_name = (
        request.POST.get("project_name", "").strip()
        or quote.project_name
    )

    # Missing checkboxes mean False.
    if "is_detection" in request.POST:
        quote.is_detection = True

    if "is_protection" in request.POST:
        quote.is_protection = True

    if "is_human_safety" in request.POST:
        quote.is_human_safety = True

    if "deliver_autocad" in request.POST:
        quote.deliver_autocad = True

    if "deliver_revit" in request.POST:
        quote.deliver_revit = True

    # Manual requirements and deliverables
    quote.manual_requirements = request.POST.get(
        "manual_requirements",
        "",
    ).strip()

    quote.manual_items_sh = request.POST.get(
        "manual_items_sh",
        "",
    ).strip()

    quote.manual_items_detection = request.POST.get(
        "manual_items_detection",
        "",
    ).strip()

    quote.manual_items_protection = request.POST.get(
        "manual_items_protection",
        "",
    ).strip()

    try:
        notes_count = int(request.POST.get("notes_count", 0))
    except (TypeError, ValueError):
        notes_count = 0

    quote.additional_notes = [
        request.POST.get(f"note_{i}", "").strip()
        for i in range(1, notes_count + 1)
        if request.POST.get(f"note_{i}", "").strip()
    ]

    def to_int(value, default):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(default or 0)

    # Payment schedule
    quote.payment_advance = to_int(
        request.POST.get("payment_advance"),
        quote.payment_advance,
    )

    quote.payment_first_version = to_int(
        request.POST.get("payment_first_version"),
        quote.payment_first_version,
    )

    quote.payment_final = to_int(
        request.POST.get("payment_final"),
        quote.payment_final,
    )

    # Delivery time
    quote.delivery_time_value = to_int(
        request.POST.get("delivery_time_value"),
        quote.delivery_time_value or 3,
    )

    valid_time_units = {"days", "weeks", "months"}
    submitted_unit = request.POST.get("delivery_time_unit", "")

    if submitted_unit in valid_time_units:
        quote.delivery_time_unit = submitted_unit

    quote.value_detection = money_to_decimal(
        request.POST.get("value_detection")
    )

    quote.value_protection = money_to_decimal(
        request.POST.get("value_protection")
    )

    quote.value_human_safety = money_to_decimal(
        request.POST.get("value_human_safety")
    )

    quote.value_detection_revit = money_to_decimal(
        request.POST.get("value_detection_revit")
    )

    quote.value_protection_revit = money_to_decimal(
        request.POST.get("value_protection_revit")
    )

    quote.value_human_safety_revit = money_to_decimal(
        request.POST.get("value_human_safety_revit")
    )

    quote.total_value = (
        quote.value_detection
        + quote.value_protection
        + quote.value_human_safety
    )

    quote.total_value_revit = (
        quote.value_detection_revit
        + quote.value_protection_revit
        + quote.value_human_safety_revit
    )

    quote.grand_total = (
        quote.total_value
        + quote.total_value_revit
    )

    quote.save()

    posted_norm_ids = [
        int(norm_id)
        for norm_id in request.POST.getlist("selected_norms")
        if str(norm_id).isdigit()
    ]

    quote.norms.set(
        Norm.objects.filter(id__in=posted_norm_ids)
    )

def generate_quote_response(quote):
    """
    Generates a Word document using the data already saved
    in the Quote model and returns it as an HTTP download.
    """

    client_requirements = parse_items(
        quote.manual_requirements
    )

    items_human_safety = parse_items(
        quote.manual_items_sh
    )

    items_protection = parse_items(
        quote.manual_items_protection
    )

    items_detection = parse_items(
        quote.manual_items_detection
    )

    additional_notes = quote.additional_notes or []

    notes_variables = build_additional_notes(
        notes=additional_notes
    )

    template_filename = get_template_filename(
        quote.is_detection,
        quote.is_protection,
        quote.is_human_safety,
        quote.deliver_autocad,
        quote.deliver_revit,
    )

    if not template_filename:
        raise FileNotFoundError(
            "No existe una plantilla para esta combinación."
        )

    template_path = os.path.join(
        settings.BASE_DIR,
        "quotes",
        "templates_docs",
        template_filename,
    )

    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"No se encontró la plantilla {template_filename}."
        )

    from datetime import datetime
    from num2words import num2words

    current_year = datetime.now().year

    meses_es = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }

    today = datetime.now()

    quote_date_es = (
        f"{today.day:02d} de "
        f"{meses_es[today.month]} de "
        f"{today.year}"
    )

    def format_bullets(items, bullet="-", indent=0, gap=6):
        valid_items = [
            str(item).strip()
            for item in items
            if item and str(item).strip()
        ]

        if not valid_items:
            return ""

        padding = "\u00A0" * indent
        spacing = "\u00A0" * gap

        return Listing(
            "\a".join(
                f"{padding}{bullet}{spacing}{item}"
                for item in valid_items
            )
        )

    reference_norms = RichText()

    for index, norm in enumerate(
        quote.norms.all().order_by("order")
    ):
        if index > 0:
            reference_norms.add(
                "\n",
                font="Cambria",
                size=22,
            )

        reference_norms.add(
            "\u00A0" * 8,
            font="Cambria",
            size=22,
        )

        reference_norms.add(
            "-",
            font="Cambria",
            size=22,
        )

        reference_norms.add(
            "\u00A0" * 6,
            font="Cambria",
            size=22,
        )

        reference_norms.add(
            (norm.code or "").strip(),
            font="Cambria",
            size=22,
        )

        description = (norm.description or "").strip()

        if description:
            reference_norms.add(
                ' "',
                font="Cambria",
                size=22,
            )

            reference_norms.add(
                description,
                font="Cambria",
                size=22,
                italic=True,
            )

            reference_norms.add(
                '"',
                font="Cambria",
                size=22,
            )

    try:
        delivery_number_text = num2words(
            quote.delivery_time_value or 0,
            lang="es",
        ).capitalize()
    except Exception:
        delivery_number_text = str(
            quote.delivery_time_value or 0
        )

    delivery_unit = (
        quote.get_delivery_time_unit_display()
        or ""
    ).lower()

    delivery_time_text = (
        f"{delivery_number_text} "
        f"({quote.delivery_time_value or 0}) "
        f"{delivery_unit} a partir del pago del anticipo."
    )

    client_title = (
        quote.client.get_title_display()
        if hasattr(quote.client, "get_title_display")
        else quote.client.title
    )

    context = {
        "quote_date": quote_date_es,
        "quote_number": (
            f"COT{quote.quote_number:03d}-"
            f"{str(quote.quote_year)[-2:]}"
        ),

        "client_city": quote.client.city or "",
        "client_company": quote.client.company or "",
        "client_title": client_title or "",
        "client_name": quote.client.full_name or "",
        "client_position": quote.client.position or "",

        "project_name_upper": (
            quote.project_name or ""
        ).upper(),

        "project_name": quote.project_name or "",

        "reference_norms": reference_norms,
        "client_requirements": format_bullets(
            client_requirements
        ),
        "items_human_safety": format_bullets(
            items_human_safety
        ),
        "items_protection": format_bullets(
            items_protection
        ),
        "items_detection": format_bullets(
            items_detection
        ),

        "sh_to_detection_space": "",

        **notes_variables,

        "payment_schedule": build_payment_schedule(
            quote.payment_advance,
            quote.payment_first_version,
            quote.payment_final,
        ),

        "delivery_time_text": delivery_time_text,
        "current_year": current_year,

        "value_protection": format_currency(
            quote.value_protection
        ),
        "value_detection": format_currency(
            quote.value_detection
        ),
        "value_human_safety": format_currency(
            quote.value_human_safety
        ),
        "total_value": format_currency(
            quote.total_value
        ),
        "total_value_text": build_total_text(
            quote.total_value
        ),

        "value_detection_revit": format_currency(
            quote.value_detection_revit
        ),
        "value_protection_revit": format_currency(
            quote.value_protection_revit
        ),
        "value_human_safety_revit": format_currency(
            quote.value_human_safety_revit
        ),
        "total_value_revit": format_currency(
            quote.total_value_revit
        ),
        "total_value_text_revit": build_total_text(
            quote.total_value_revit
        ),

        "grand_total": format_currency(
            quote.grand_total
        ),
    }

    output_filename = build_output_filename(quote)

    output_directory = os.path.join(
        settings.BASE_DIR,
        "generated_docs",
    )

    os.makedirs(
        output_directory,
        exist_ok=True,
    )

    output_path = os.path.join(
        output_directory,
        output_filename,
    )

    from .services.document_service import generate_doc

    generate_doc(
        template_path,
        context,
        output_path,
    )

    with open(output_path, "rb") as generated_file:
        response = HttpResponse(
            generated_file.read(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )

    response["Content-Disposition"] = (
        f'attachment; filename="{output_filename}"'
    )

    return response

# View: manage quote details and generate the final Word document
def quote_details(request, quote_id):
    quote = get_object_or_404(
        Quote.objects.select_related("client"),
        id=quote_id,
    )

    norms = Norm.objects.all().order_by("order")

    if request.method == "POST":
        save_quote_details(quote, request)

        action = request.POST.get(
            "form_action",
            "generate",
        )

        if action == "save":
            messages.success(
                request,
                "Cotización actualizada correctamente.",
            )

            return redirect(
                "quote_info",
                quote_id=quote.id,
            )

        try:
            return generate_quote_response(quote)

        except FileNotFoundError as error:
            messages.error(
                request,
                str(error),
            )

            return redirect(
                "quote_details",
                quote_id=quote.id,
            )

        except Exception as error:
            messages.error(
                request,
                f"No fue posible generar el documento: {error}",
            )

            return redirect(
                "quote_details",
                quote_id=quote.id,
            )

    selected_norm_ids = set(
        quote.norms.values_list(
            "id",
            flat=True,
        )
    )

    default_norm_ids = set()

    # Use service defaults only when no norms have been saved yet.
    if not selected_norm_ids:
        if quote.is_detection:
            default_norm_ids.update(
                Norm.objects.filter(
                    default_detection=True
                ).values_list(
                    "id",
                    flat=True,
                )
            )

        if quote.is_protection:
            default_norm_ids.update(
                Norm.objects.filter(
                    default_protection=True
                ).values_list(
                    "id",
                    flat=True,
                )
            )

        if quote.is_human_safety:
            default_norm_ids.update(
                Norm.objects.filter(
                    default_human_safety=True
                ).values_list(
                    "id",
                    flat=True,
                )
            )

    saved_notes = list(
        enumerate(
            quote.additional_notes or [],
            start=1,
        )
    )

    return render(
        request,
        "quotes/quote_details.html",
        {
            "quote": quote,
            "notes_range": range(1, 11),
            "norms": norms,
            "selected_norm_ids": selected_norm_ids,
            "default_norm_ids": default_norm_ids,
            "saved_notes": saved_notes,
            "saved_notes_count": len(saved_notes),
            "edit_mode": False,
        },
    )

def quote_update(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)
    norms = Norm.objects.all().order_by("order")

    if request.method == "POST":
        save_quote_details(quote, request)

        messages.success(
            request,
            "Cotización actualizada correctamente.",
        )

        return redirect(
            "quote_info",
            quote_id=quote.id,
        )

    selected_norm_ids = set(
        quote.norms.values_list("id", flat=True)
    )

    saved_notes = list(
        enumerate(
            quote.additional_notes or [],
            start=1,
        )
    )

    return render(
        request,
        "quotes/quote_details.html",
        {
            "quote": quote,
            "norms": norms,
            "notes_range": range(1, 11),
            "selected_norm_ids": selected_norm_ids,
            "default_norm_ids": set(),
            "saved_notes": saved_notes,
            "saved_notes_count": len(saved_notes),
            "edit_mode": True,
        },
    )

def home(request):
    can_download_backup = (
        request.user.is_authenticated
        and (
            request.user.is_superuser
            or request.user.groups.filter(
                name="User Managers"
            ).exists()
        )
    )

    return render(
        request,
        "quotes/home.html",
        {
            "can_download_backup": can_download_backup,
        },
    )


def client_list(request):
    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_clients")

        if selected_ids:
            Client.objects.filter(id__in=selected_ids).delete()
            messages.success(request, "Clientes seleccionados eliminados correctamente.")
        else:
            messages.error(request, "Selecciona al menos un cliente para eliminar.")

        return redirect("client_list")

    query = request.GET.get("q", "").strip()

    clients = Client.objects.all().order_by("full_name")

    if query:
        search_terms = query.split()

        for term in search_terms:
            clients = clients.filter(
                Q(full_name__icontains=term) |
                Q(company__icontains=term)
            )

        clients = clients.distinct().order_by("full_name")

    return render(
        request,
        "quotes/client_list.html",
        {
            "clients": clients,
            "query": query,
        }
    )


def client_detail(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    quotes = client.quotes.all().order_by("-created_at")

    return render(
        request,
        "quotes/client_detail.html",
        {
            "client": client,
            "quotes": quotes,
        }
    )

def client_delete(request, client_id):
    client = get_object_or_404(Client, id=client_id)

    if request.method == "POST":
        client.delete()
        messages.success(request, "Cliente eliminado correctamente.")
        return redirect("client_list")

    return redirect("client_detail", client_id=client.id)

def quote_list(request):
    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_quotes")

        if selected_ids:
            Quote.objects.filter(id__in=selected_ids).delete()
            messages.success(request, "Cotizaciones seleccionadas eliminadas correctamente.")
        else:
            messages.error(request, "Selecciona al menos una cotización para eliminar.")

        return redirect("quote_list")

    query = request.GET.get("q", "").strip()

    quotes = Quote.objects.select_related("client").all().order_by("-created_at")

    if query:
        quotes = quotes.filter(
            project_name__icontains=query
        ) | Quote.objects.select_related("client").filter(
            client__full_name__icontains=query
        ) | Quote.objects.select_related("client").filter(
            client__company__icontains=query
        )

        quotes = quotes.distinct().order_by("-created_at")

    return render(
        request,
        "quotes/quote_list.html",
        {
            "quotes": quotes,
            "query": query,
        }
    )


def quote_info(request, quote_id):
    quote = get_object_or_404(
        Quote.objects.select_related("client"),
        id=quote_id
    )

    return render(
        request,
        "quotes/quote_info.html",
        {
            "quote": quote,
            "total_autocad": format_currency(quote.total_value),
            "total_revit": format_currency(quote.total_value_revit),
        }
    )

def quote_download(request, quote_id):
    quote = get_object_or_404(
        Quote.objects.select_related("client"),
        id=quote_id,
    )

    try:
        return generate_quote_response(quote)

    except FileNotFoundError as error:
        messages.error(
            request,
            str(error),
        )

        return redirect(
            "quote_info",
            quote_id=quote.id,
        )

    except Exception as error:
        messages.error(
            request,
            f"No fue posible generar el documento: {error}",
        )

        return redirect(
            "quote_info",
            quote_id=quote.id,
        )

def quote_delete(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)

    if request.method == "POST":
        client_id = quote.client.id
        quote.delete()
        messages.success(request, "Cotización eliminada correctamente.")
        return redirect("client_detail", client_id=client_id)

    return redirect("quote_info", quote_id=quote.id)

def client_update(request, client_id):
    client = get_object_or_404(Client, id=client_id)

    if request.method == "POST":
        client.title = request.POST.get("title", "")
        client.full_name = request.POST.get("full_name", "")
        client.position = request.POST.get("position", "")
        client.company = request.POST.get("company", "")
        client.city = request.POST.get("city", "")
        client.email = request.POST.get("email", "")
        client.phone = request.POST.get("phone", "")

        client.save()

        messages.success(request, "Cliente actualizado correctamente.")
        return redirect("client_detail", client_id=client.id)

    return render(
        request,
        "quotes/client_update.html",
        {
            "client": client,
        }
    )

def can_download_backup(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.groups.filter(name="User Managers").exists()
    )

@login_required
def generate_quotes_report(request):
    """
    Descarga el reporte completo de seguimiento a cotizaciones.

    Conserva las hojas históricas de la plantilla y actualiza
    automáticamente las hojas desde 2026 en adelante.
    """
    if request.method != "GET":
        return redirect("quote_list")

    quotes = (
        Quote.objects
        .select_related(
            "client",
            "template_doc",
        )
        .prefetch_related("norms")
        .filter(
            quote_year__isnull=False,
            quote_year__gte=2026,
        )
        .order_by(
            "quote_year",
            "quote_number",
            "created_at",
            "id",
        )
    )

    try:
        excel_file = generate_quotes_excel_report(
            quotes=quotes,
        )
    except (FileNotFoundError, ValueError) as error:
        messages.error(
            request,
            str(error),
        )
        return redirect("quote_list")

    except Exception as error:
        print("EXCEL REPORT ERROR:", repr(error))

        messages.error(
            request,
            f"No fue posible generar el reporte: {error}"
        )

        return redirect("quote_list")
    # except Exception:
    #     messages.error(
    #         request,
    #         "No fue posible generar el reporte de cotizaciones."
    #     )
    #     return redirect("quote_list")

    filename = "Seguimiento a cotizaciones.xlsx"

    response = HttpResponse(
        excel_file.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    return response

@login_required
@user_passes_test(can_download_backup)
def download_backup(request):
    """
    Descarga un fixture JSON comprimido progresivamente.

    Los registros se leen y envían por bloques pequeños para evitar
    cargar toda la base de datos en la memoria del servidor.
    """

    def generate_json_fixture():
        """
        Produce un fixture JSON válido compatible con loaddata.
        """
        yield b"[\n"

        first_object = True

        model_querysets = [
            Client.objects.all().order_by("id").iterator(
                chunk_size=200
            ),

            Norm.objects.all().order_by("id").iterator(
                chunk_size=200
            ),

            TemplateDoc.objects.all().order_by("id").iterator(
                chunk_size=100
            ),

            QuoteCounter.objects.all().order_by("id").iterator(
                chunk_size=100
            ),

            Quote.objects.select_related(
                "client",
                "template_doc",
            ).prefetch_related(
                "norms"
            ).order_by(
                "id"
            ).iterator(
                chunk_size=50
            ),
        ]

        for queryset in model_querysets:
            for instance in queryset:
                serialized = serializers.serialize(
                    "json",
                    [instance],
                    use_natural_foreign_keys=False,
                    use_natural_primary_keys=False,
                )

                # serializers.serialize devuelve:
                # [{"model": ..., "pk": ..., "fields": ...}]
                # Quitamos los corchetes externos para construir
                # un único fixture con todos los registros.
                serialized_object = serialized[1:-1].strip()

                if not serialized_object:
                    continue

                if not first_object:
                    yield b",\n"

                yield serialized_object.encode("utf-8")
                first_object = False

        yield b"\n]"

    def generate_compressed_backup():
        """
        Comprime progresivamente sin guardar el resultado completo
        en memoria ni en una variable.
        """
        compressor = zlib.compressobj(
            level=5,
            method=zlib.DEFLATED,
            wbits=31,  # Genera formato gzip.
        )

        for json_chunk in generate_json_fixture():
            compressed_chunk = compressor.compress(
                json_chunk
            )

            if compressed_chunk:
                yield compressed_chunk

        final_chunk = compressor.flush()

        if final_chunk:
            yield final_chunk

    backup_date = timezone.localdate().strftime(
        "%Y-%m-%d"
    )

    filename = (
        f"firequote_backup_{backup_date}.json.gz"
    )

    response = StreamingHttpResponse(
        streaming_content=generate_compressed_backup(),
        content_type="application/gzip",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    response["X-Content-Type-Options"] = "nosniff"

    return response