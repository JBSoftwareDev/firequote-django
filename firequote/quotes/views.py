from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from docxtpl import DocxTemplate
import os
from datetime import datetime
from .models import Quote, Client, Norm
from django.conf import settings

"""
quotes/views.py
---------------
Handles quote creation, editing, and document generation (.docx)
for the FireQuote Django web application.
"""

# Utility: converts multiline text input into a clean list of items
def parse_items(text):
    if not text:
        return []
    return [i.strip() for i in text.split("\n") if i.strip()]

# Determine the correct .docx template based on selected services and delivery formats
def get_template_filename(is_detection, is_protection, is_human_safety, deliver_autocad, deliver_revit):
    # Determine base name based on service combination
    if is_detection and is_protection and is_human_safety:
        base_name = "detection_protection_human_safety"
    elif is_detection and is_protection:
        base_name = "detection_protection"
    elif is_detection and is_human_safety:
        base_name = "detection_human_safety"
    elif is_protection and is_human_safety:
        base_name = "protection_human_safety"
    elif is_detection:
        base_name = "detection"
    elif is_protection:
        base_name = "protection"
    elif is_human_safety:
        base_name = "human_safety"
    else:
        return None

    # Determine suffix based on delivery format (AutoCAD/Revit)
    if deliver_autocad and deliver_revit:
        suffix = "_both"
    elif deliver_autocad:
        suffix = "_autocad"
    elif deliver_revit:
        suffix = "_revit"
    else:
        suffix = ""

    filename = f"{base_name}{suffix}.docx"
    return filename

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

        # Create the quote record with service and format options
        quote = Quote.objects.create(
            client_id=client_id,
            project_name=project_name,
            service_tag=service_tag,
            delivery_time_value=delivery_time_value,
            delivery_time_unit=delivery_time_unit,

            is_detection=('is_detection' in request.POST),
            is_protection=('is_protection' in request.POST),
            is_human_safety=('is_human_safety' in request.POST),
            deliver_autocad=('deliver_autocad' in request.POST),
            deliver_revit=('deliver_revit' in request.POST),
        )

        messages.success(request, "Cotización creada correctamente.")
        return redirect("quote_details", quote_id=quote.id)

    # On GET: render the empty quote creation form
    return render(request, "quotes/quote_form.html", {"clients": clients})


# View: manage quote details and generate the final Word (.docx) report
def quote_details(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)

    # Load all available reference norms for display
    norms = Norm.objects.all().order_by("code")

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

        quote.payment_advance = int(payment_advance) if str(payment_advance).isdigit() else quote.payment_advance
        quote.payment_first_version = int(payment_first_version) if str(
            payment_first_version).isdigit() else quote.payment_first_version
        quote.payment_final = int(payment_final) if str(payment_final).isdigit() else quote.payment_final
        quote.delivery_time_value = int(delivery_time_value) if str(
            delivery_time_value).isdigit() else quote.delivery_time_value
        quote.delivery_time_unit = delivery_time_unit or quote.delivery_time_unit
        quote.save()

        # Select the appropriate Word template based on chosen options
        template_filename = get_template_filename(
            is_detection=quote.is_detection,
            is_protection=quote.is_protection,
            is_human_safety=quote.is_human_safety,
            deliver_autocad=quote.deliver_autocad,
            deliver_revit=quote.deliver_revit,
        )

        # Handle default vs. user-selected reference norms
        posted_norm_ids = request.POST.getlist("selected_norms")  # viene como lista de strings
        # Safely convert submitted IDs to integers
        try:
            posted_norm_ids = [int(i) for i in posted_norm_ids if i and str(i).isdigit()]
        except ValueError:
            posted_norm_ids = []

        if posted_norm_ids:
            # Use user-selected norms if any were checked
            selected_norms_qs = Norm.objects.filter(id__in=posted_norm_ids)
        else:
            # Otherwise, fall back to default norms
            selected_norms_qs = Norm.objects.filter(is_default=True)

        # Replace previous norms assigned to this quote
        quote.norms.set(selected_norms_qs)
        quote.save()

        # Select the appropriate Word (.docx) template
        template_filename = get_template_filename(
            is_detection=quote.is_detection,
            is_protection=quote.is_protection,
            is_human_safety=quote.is_human_safety,
            deliver_autocad=quote.deliver_autocad,
            deliver_revit=quote.deliver_revit
        )

        # Validate that a template exists before rendering
        if not template_filename:
            messages.error(
                request,
                "No se seleccionó ningún servicio, por favor marca al menos uno."
            )
            return redirect("quote_form")

        template_path = os.path.join(settings.BASE_DIR, "quotes", "templates_docs", template_filename)

        if not os.path.exists(template_path):
            messages.error(
                request,
                f"No se encontró la plantilla correspondiente: {template_filename}"
            )
            return redirect("quote_form")

        import locale
        from datetime import datetime

        # Helpers: format bullet-point text for correct Word rendering
        def format_bullets(items, bullet="-"):
            # Format a list of items as bullet points with a tab after the bullet. Example: "-\tItem text"
            if not items:
                return ""
            return "\n".join(f"{bullet}\t{i.strip()}" for i in items if i and str(i).strip())

        def format_bullets_no_tab(items, bullet='-'):
            # Format a list of items as bullet points without a tab character.
            if not items:
                return ""
            return "\n".join(f"{bullet} {i.strip()}" for i in items if i and str(i).strip())

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
        reference_norms = [f"{n.code} {n.description}".strip() for n in quote.norms.all()]

        # Get display title (Mr./Mrs.) from client model
        if hasattr(quote.client, "get_title_display"):
            client_title = quote.client.get_title_display()
        else:
            client_title = getattr(quote.client, "title", "") or ""

        # Context data for the Word template
        context = {
            "quote_date": quote_date_es,
            "quote_number": f"COT{quote.id:03d}-25",

            "client_city": getattr(quote.client, "city", "") or "",
            "client_company": getattr(quote.client, "company", "") or "",
            "client_title": client_title,
            "client_name": quote.client.full_name,
            "client_position": getattr(quote.client, "position", "") or "",

            "project_name": quote.project_name,

            "reference_norms": format_bullets(reference_norms, bullet="•"),  # ← punto
            "client_requirements": format_bullets(client_requirements),  # ← guion
            "items_human_safety": format_bullets(items_human_safety),
            "items_protection": format_bullets(items_protection),
            "items_detection": format_bullets(items_detection),
            "additional_notes": format_bullets_no_tab(additional_notes, "-"),
            "payment_schedule": format_bullets_no_tab([
                f"{quote.payment_advance}% Anticipo",
                f"{quote.payment_first_version}% Contra entrega de la primera versión del diseño",
                f"{quote.payment_final}% Contra entrega final del diseño",
            ], "-"),

            "delivery_time_text": f"{quote.delivery_time_value} {quote.get_delivery_time_unit_display()} a partir del pago del anticipo.",

            "value_protection": getattr(quote, "value_protection", ""),
            "value_detection": getattr(quote, "value_detection", ""),
            "value_human_safety": getattr(quote, "value_human_safety", ""),
            "total_value": getattr(quote, "total_value", ""),
            "total_value_text": getattr(quote, "total_value_text", ""),
        }

        doc = DocxTemplate(template_path)
        doc.render(context)

        # Save the generated .docx file to the output directory
        safe_client_name = "".join(c for c in quote.client.full_name if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        safe_project = "".join(c for c in quote.project_name if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        output_filename = f"Cotizacion_{safe_client_name}_{safe_project}.docx"
        os.makedirs(os.path.join(settings.BASE_DIR, "generated_docs"), exist_ok=True)
        output_path = os.path.join(settings.BASE_DIR, "generated_docs", output_filename)
        doc.save(output_path)

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
    default_norm_ids = set(Norm.objects.filter(is_default=True).values_list('id', flat=True))
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
