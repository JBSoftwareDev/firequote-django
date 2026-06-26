from .services.quote_service import (
    calculate_prices,
    format_currency,
    parse_items,
    build_total_text,
    build_additional_notes,
    build_payment_schedule,
    get_template_filename,
    build_output_filename,
)
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Q
import locale
import os
from .models import Quote, Client, Norm, TemplateDoc
from django.conf import settings
from docxtpl import Listing, RichText

"""
quotes/views.py
---------------
Handles quote creation, editing, and document generation (.docx)
for the FireQuote Django web application.
"""

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

        # Create the quote record with service and format options
        quote = Quote.objects.create(
            client=client,
            project_name=project_name,
            service_tag=service_tag,
            delivery_time_value=delivery_time_value,
            delivery_time_unit=delivery_time_unit,

            building_type=request.POST.get("building_type"),
            area_sqm=float(request.POST.get("m2", 0)),

            is_detection=('is_detection' in request.POST),
            is_protection=('is_protection' in request.POST),
            is_human_safety=('is_human_safety' in request.POST),
            deliver_autocad=('deliver_autocad' in request.POST),
            deliver_revit=('deliver_revit' in request.POST),
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


# View: manage quote details and generate the final Word (.docx) report
def quote_details(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)

    # Load all available reference norms for display
    norms = Norm.objects.all().order_by("order")

    # Parse text inputs into structured lists
    if request.method == "POST":
        client_requirements = parse_items(request.POST.get("manual_requirements", ""))
        items_human_safety = parse_items(request.POST.get("manual_items_sh", ""))
        items_protection = parse_items(request.POST.get("manual_items_protection", ""))
        items_detection = parse_items(request.POST.get("manual_items_detection", ""))

        notes_count = int(request.POST.get("notes_count", 0))
        additional_notes = [
            request.POST.get(f"note_{i}", "").strip()
            for i in range(1, notes_count + 1)
            if request.POST.get(f"note_{i}", "").strip()
        ]

        notes_variables = build_additional_notes(
            notes=additional_notes
        )

        print("DEBUG NOTES:")
        print(notes_variables)

        payment_advance = request.POST.get("payment_advance", "")
        payment_first_version = request.POST.get("payment_first_version", "")
        payment_final = request.POST.get("payment_final", "")
        delivery_time_value = request.POST.get("delivery_time_value", "")
        delivery_time_unit = request.POST.get("delivery_time_unit", "")

        # Normalize checkbox input (HTML sends "on"/"true"/None inconsistently)
        def str2bool(v):
            return str(v).lower() in ("true", "1", "yes", "on")

        quote.is_detection = str2bool(request.POST.get("is_detection", quote.is_detection))
        quote.is_protection = str2bool(request.POST.get("is_protection", quote.is_protection))
        quote.is_human_safety = str2bool(request.POST.get("is_human_safety", quote.is_human_safety))
        quote.deliver_autocad = str2bool(request.POST.get("deliver_autocad", quote.deliver_autocad))
        quote.deliver_revit = str2bool(request.POST.get("deliver_revit", quote.deliver_revit))

        def to_int(value, default):
            try:
                return int(float(value))
            except:
                return default

        quote.payment_advance = to_int(payment_advance, quote.payment_advance)
        quote.payment_first_version = to_int(payment_first_version, quote.payment_first_version)
        quote.payment_final = to_int(payment_final, quote.payment_final)
        quote.delivery_time_value = int(delivery_time_value) if str(delivery_time_value).isdigit() else 3
        quote.delivery_time_unit = delivery_time_unit or "semanas"
        quote.delivery_time_unit = delivery_time_unit or quote.delivery_time_unit
        quote.save()

        # Handle default vs. user-selected reference norms
        posted_norm_ids = request.POST.getlist("selected_norms")  # viene como lista de strings
        # Safely convert submitted IDs to integers
        try:
            posted_norm_ids = [int(i) for i in posted_norm_ids if i and str(i).isdigit()]
        except ValueError:
            posted_norm_ids = []

        if posted_norm_ids:
            selected_norms_qs = Norm.objects.filter(id__in=posted_norm_ids)
        else:
            selected_norms_qs = Norm.objects.none()

            if quote.is_detection:
                selected_norms_qs = selected_norms_qs | Norm.objects.filter(default_detection=True)

            if quote.is_protection:
                selected_norms_qs = selected_norms_qs | Norm.objects.filter(default_protection=True)

            if quote.is_human_safety:
                selected_norms_qs = selected_norms_qs | Norm.objects.filter(default_human_safety=True)

            selected_norms_qs = selected_norms_qs.distinct().order_by("order")

        # Replace previous norms assigned to this quote
        quote.norms.set(selected_norms_qs)
        quote.save()

        # =========================
        # BUILD TEMPLATE TAGS
        # =========================

        services = []

        if quote.is_detection:
            services.append("detection")
        if quote.is_protection:
            services.append("protection")
        if quote.is_human_safety:
            services.append("human_safety")

        services_tag = "_".join(services)

        formats = []

        if quote.deliver_autocad and quote.deliver_revit:
            formats_tag = "both"
        elif quote.deliver_autocad:
            formats_tag = "autocad"
        elif quote.deliver_revit:
            formats_tag = "revit"
        else:
            formats_tag = ""

        print("DEBUG SERVICES:", services_tag)
        print("DEBUG FORMAT:", formats_tag)

        # =========================
        # GET TEMPLATE FROM DATABASE
        # =========================

        template = TemplateDoc.objects.filter(
            services_tag=services_tag,
            formats_tag=formats_tag
        ).first()

        if not template:
            messages.error(request, "No existe plantilla configurada para esta combinación.")
            return redirect("quote_form")

        template_filename = get_template_filename(
            quote.is_detection,
            quote.is_protection,
            quote.is_human_safety,
            quote.deliver_autocad,
            quote.deliver_revit,
        )

        template_path = os.path.join(
            settings.BASE_DIR,
            "quotes",
            "templates_docs",
            template_filename,
        )

        import locale
        from datetime import datetime

        current_year = datetime.now().year
        current_year_short = str(current_year)[-2:]

        # Helpers: format bullet-point text for correct Word rendering
        def format_bullets(items, bullet="-", indent=0, gap=6):
            valid_items = [
                str(i).strip()
                for i in items
                if i and str(i).strip()
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

        # Format date in Spanish (fallback for Windows locale issues)
        try:
            locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
        except locale.Error:
            try:
                locale.setlocale(locale.LC_TIME, "Spanish_Spain")
            except locale.Error:
                meses_es = {
                    "January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
                    "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
                    "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"
                }
                fecha_en = datetime.now().strftime("%d de %B de %Y")
                for en, es in meses_es.items():
                    fecha_en = fecha_en.replace(en, es)
                quote_date_es = fecha_en
            else:
                quote_date_es = datetime.now().strftime("%d de %B de %Y")
        else:
            quote_date_es = datetime.now().strftime("%d de %B de %Y")

        # Build formatted list of reference norms
        # Build formatted list of reference norms
        # Build formatted list of reference norms with italic descriptions
        reference_norms = RichText()

        FONT_NAME = "Cambria"
        FONT_SIZE = 22  # 11 pt en Word

        for index, n in enumerate(quote.norms.all().order_by("order")):

            code = (n.code or "").strip()
            description = (n.description or "").strip()

            if index > 0:
                reference_norms.add(
                    "\n",
                    font=FONT_NAME,
                    size=FONT_SIZE
                )

            reference_norms.add(
                "\u00A0" * 8,
                font=FONT_NAME,
                size=FONT_SIZE
            )

            reference_norms.add(
                "-",
                font=FONT_NAME,
                size=FONT_SIZE
            )

            reference_norms.add(
                "\u00A0" * 6,
                font=FONT_NAME,
                size=FONT_SIZE
            )

            reference_norms.add(
                code,
                font=FONT_NAME,
                size=FONT_SIZE
            )

            if description:
                reference_norms.add(
                    ' "',
                    font=FONT_NAME,
                    size=FONT_SIZE
                )

                reference_norms.add(
                    description,
                    font=FONT_NAME,
                    size=FONT_SIZE,
                    italic=True
                )

                reference_norms.add(
                    '"',
                    font=FONT_NAME,
                    size=FONT_SIZE
                )

        # Get display title (Mr./Mrs.) from client model
        if hasattr(quote.client, "get_title_display"):
            client_title = quote.client.get_title_display()
        else:
            client_title = getattr(quote.client, "title", "") or ""

        # =========================
        # CALCULATE PRICES
        # =========================
        from num2words import num2words

        def numero_a_texto(numero):
            try:
                return num2words(numero, lang="es").capitalize()
            except:
                return str(numero)

        prices = calculate_prices(
            area_sqm=float(quote.area_sqm or 0),
            building_type=quote.building_type,
            services={
                "detection": quote.is_detection,
                "protection": quote.is_protection,
                "human_safety": quote.is_human_safety,
            },
            formats={
                "autocad": quote.deliver_autocad,
                "revit": quote.deliver_revit,
            }
        )

        total_value_text = build_total_text(prices["total_autocad"])
        total_value_text_revit = build_total_text(prices["total_revit"])

        # -------------------------
        # AUTOCAD (saved in model)
        # -------------------------
        quote.value_detection = prices["detection_autocad"]
        quote.value_protection = prices["protection_autocad"]
        quote.value_human_safety = prices["human_safety_autocad"]
        quote.total_value = prices["total_autocad"]

        quote.save()

        # -------------------------
        # REVIT (only for template)
        # -------------------------
        value_detection_revit = prices["detection_revit"]
        value_protection_revit = prices["protection_revit"]
        value_human_safety_revit = prices["human_safety_revit"]
        total_value_revit = prices["total_revit"]

        # -------------------------
        # FINAL TOTAL (optional)
        # -------------------------
        grand_total = prices["grand_total"]

        # -------------------------
        # TEXT FOR SINGLE SERVICE TEMPLATES
        # -------------------------

        total_value_text = f"El valor todal de la propuesta es {format_currency(quote.total_value)}"
        total_value_text_revit = f"El valor total de la propuesta es {format_currency(total_value_revit)}"

        # -------------------------
        # DELIVERY TIME TEXT
        # -------------------------
        valor = quote.delivery_time_value or 0

        # Forzar minúsculas en unidad
        unidad = (quote.get_delivery_time_unit_display() or "").lower()

        # Número en letras
        valor_letras = numero_a_texto(valor)

        delivery_time_text = f"{valor_letras} ({valor}) {unidad} a partir del pago del anticipo."
        total_value_text = build_total_text(quote.total_value)
        total_value_text_revit = build_total_text(total_value_revit)

        # Context data for the Word template
        context = {
            "quote_date": quote_date_es,
            "quote_number": f"COT{quote.id:03d}-{current_year_short}",

            "client_city": getattr(quote.client, "city", "") or "",
            "client_company": getattr(quote.client, "company", "") or "",
            "client_title": client_title,
            "client_name": quote.client.full_name,
            "client_position": getattr(quote.client, "position", "") or "",

            "project_name_upper": (quote.project_name or "").upper(),
            "project_name": quote.project_name,

            "reference_norms": reference_norms,
            "client_requirements": format_bullets(client_requirements),
            "items_human_safety": format_bullets(items_human_safety),
            "items_protection": format_bullets(items_protection),
            "items_detection": format_bullets(items_detection),
            "sh_to_detection_space": "",
            **notes_variables,
            "payment_schedule": build_payment_schedule(
                quote.payment_advance,
                quote.payment_first_version,
                quote.payment_final,
            ),

            "delivery_time_text": delivery_time_text,
            "current_year": current_year,

            # -------------------------
            # AUTOCAD
            # -------------------------
            "value_protection": format_currency(quote.value_protection),
            "value_detection": format_currency(quote.value_detection),
            "value_human_safety": format_currency(quote.value_human_safety),
            "total_value": format_currency(quote.total_value),
            "total_value_text": total_value_text,

            # -------------------------
            # REVIT
            # -------------------------
            "value_detection_revit": format_currency(value_detection_revit),
            "value_protection_revit": format_currency(value_protection_revit),
            "value_human_safety_revit": format_currency(value_human_safety_revit),
            "total_value_revit": format_currency(total_value_revit),
            "total_value_text_revit": total_value_text_revit,

            # OPTIONAL
            "grand_total": format_currency(grand_total),
        }
                                                                                                       "_")
        output_filename = build_output_filename(quote)
        os.makedirs(os.path.join(settings.BASE_DIR, "generated_docs"), exist_ok=True)
        output_path = os.path.join(settings.BASE_DIR, "generated_docs", output_filename)

        from .services.document_service import generate_doc

        generate_doc(template_path, context, output_path)

        # Return the generated file as a downloadable response
        with open(output_path, "rb") as f:
            response = HttpResponse(
                f.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            response["Content-Disposition"] = f'attachment; filename="{output_filename}"'
            return response

    # On GET: render quote detail page with all norms and notes
    notes_range = range(1, 11)
    # Pass all norms to the template and mark the selected or default ones as checked
    selected_norm_ids = set(quote.norms.values_list('id', flat=True))
    selected_services = []

    if quote.is_detection:
        selected_services.append("detection")
    if quote.is_protection:
        selected_services.append("protection")
    if quote.is_human_safety:
        selected_services.append("human_safety")

    default_norm_ids = set()

    if quote.is_detection:
        default_norm_ids.update(
            Norm.objects.filter(default_detection=True).values_list("id", flat=True)
        )

    if quote.is_protection:
        default_norm_ids.update(
            Norm.objects.filter(default_protection=True).values_list("id", flat=True)
        )

    if quote.is_human_safety:
        default_norm_ids.update(
            Norm.objects.filter(default_human_safety=True).values_list("id", flat=True)
        )

    return render(
        request,
        "quotes/quote_details.html",
        {
            "quote": quote,
            "notes_range": notes_range,
            "norms": norms,
            "selected_norm_ids": selected_norm_ids,
            "default_norm_ids": default_norm_ids,
        },
    )

def home(request):
    return render(request, "quotes/home.html")


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

    prices = calculate_prices(
        area_sqm=float(quote.area_sqm or 0),
        building_type=quote.building_type,
        services={
            "detection": quote.is_detection,
            "protection": quote.is_protection,
            "human_safety": quote.is_human_safety,
        },
        formats={
            "autocad": quote.deliver_autocad,
            "revit": quote.deliver_revit,
        }
    )

    return render(
        request,
        "quotes/quote_info.html",
        {
            "quote": quote,
            "total_autocad": format_currency(prices["total_autocad"]),
            "total_revit": format_currency(prices["total_revit"]),
        }
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