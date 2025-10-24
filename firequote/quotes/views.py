from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from docxtpl import DocxTemplate
import os
from datetime import datetime
from .models import Quote, Client  # Asegúrate de importar Client


# --- Función auxiliar: convierte texto multilinea en lista ---
def parse_items(text):
    if not text:
        return []
    return [i.strip() for i in text.split("\n") if i.strip()]

# --- Función para determinar nombre de plantilla según servicios y formatos ---
# --- Función para determinar nombre de plantilla según servicios y formatos ---
def get_template_filename(is_detection, is_protection, is_human_safety, deliver_autocad, deliver_revit):
    # Determinar combinación de servicios según tus 21 plantillas
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
        return None  # Ningún servicio seleccionado

    # Determinar formato de entrega
    if deliver_autocad and deliver_revit:
        base_name += "_both"
    elif deliver_autocad:
        base_name += "_autocad"
    elif deliver_revit:
        base_name += "_revit"

    return f"{base_name}.docx"

# --- Vista principal: formulario para crear una cotización ---
def quote_form(request):
    clients = Client.objects.all()  # para llenar el dropdown de clientes existentes

    if request.method == "POST":
        client_id = request.POST.get("existing_client")
        project_name = request.POST.get("project_name")
        service_tag = request.POST.get("service_tag") or "default"  # poner valor por defecto si no existe
        delivery_time_value = request.POST.get("delivery_time_value") or 0
        delivery_time_unit = request.POST.get("delivery_time_unit") or "days"

        # Si no se seleccionó cliente existente, revisar si se llenó cliente nuevo
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

        # Validar campos obligatorios
        if not all([client_id, project_name]):
            messages.error(request, "Por favor completa todos los campos obligatorios.")
            return redirect("quote_form")

        # Crear la cotizac
        # ión
        quote = Quote.objects.create(
            client_id=client_id,
            project_name=project_name,
            service_tag=service_tag,
            delivery_time_value=delivery_time_value,
            delivery_time_unit=delivery_time_unit,
        )

        messages.success(request, "Cotización creada correctamente.")
        return redirect("quote_details", quote_id=quote.id)

    # Si es GET, mostrar formulario vacío con clientes existentes
    return render(request, "quotes/quote_form.html", {"clients": clients})


# --- Vista de detalles: agregar ítems, notas y generar DOCX ---
def quote_details(request, quote_id):
    quote = get_object_or_404(Quote, id=quote_id)

    if request.method == "POST":
        # Capturar campos desde el formulario
        client_requirements = parse_items(request.POST.get("manual_requirements", ""))
        items_human_safety = parse_items(request.POST.get("manual_items_sh", ""))
        items_protection = parse_items(request.POST.get("manual_items_protection", ""))
        items_detection = parse_items(request.POST.get("manual_items_detection", ""))

        # Notas adicionales (pueden estar vacías)
        notes_count = int(request.POST.get("notes_count", 0))
        additional_notes = [
            request.POST.get(f"note_{i}", "")
            for i in range(1, notes_count + 1)
            if request.POST.get(f"note_{i}", "")
        ]

        # Datos de pago y entrega
        payment_advance = request.POST.get("payment_advance", "")
        payment_first_version = request.POST.get("payment_first_version", "")
        payment_final = request.POST.get("payment_final", "")
        delivery_time_value = request.POST.get("delivery_time_value", "")
        delivery_time_unit = request.POST.get("delivery_time_unit", "")

        # --- Actualizar servicios y formatos según lo que vino del formulario ---
        def str2bool(value):
            return str(value).lower() in ("true", "1", "yes")

        quote.is_detection = str2bool(request.POST.get('is_detection'))
        quote.is_protection = str2bool(request.POST.get('is_protection'))
        quote.is_human_safety = str2bool(request.POST.get('is_human_safety'))
        quote.deliver_autocad = str2bool(request.POST.get('deliver_autocad'))
        quote.deliver_revit = str2bool(request.POST.get('deliver_revit'))

        # Guardar temporalmente para usar en get_template_filename
        quote.save()

        # Determinar plantilla .docx a usar
        template_filename = get_template_filename(
            is_detection=quote.is_detection,
            is_protection=quote.is_protection,
            is_human_safety=quote.is_human_safety,
            deliver_autocad=quote.deliver_autocad,
            deliver_revit=quote.deliver_revit
        )

        if not template_filename:
            messages.error(
                request,
                "No se seleccionó ningún servicio, por favor marca al menos uno."
            )
            return redirect("quote_form")

        template_path = os.path.join("templates_docs", template_filename)

        if not os.path.exists(template_path):
            messages.error(
                request,
                f"No se encontró la plantilla correspondiente: {template_filename}"
            )
            return redirect("quote_form")

        # Construir ruta del archivo
        template_path = os.path.join("templates_docs", template_filename)

        # Validar existencia del archivo
        if not os.path.exists(template_path):
            messages.error(
                request,
                f"No se encontró la plantilla correspondiente: {template_filename}"
            )
            return redirect("quote_form")

        # Renderizar plantilla con contexto
        doc = DocxTemplate(template_path)
        context = {
            "client_name": quote.client.full_name,
            "project_name": quote.project_name,
            "client_requirements": client_requirements,
            "items_human_safety": items_human_safety,
            "items_protection": items_protection,
            "items_detection": items_detection,
            "additional_notes": additional_notes,
            "payment_advance": payment_advance,
            "payment_first_version": payment_first_version,
            "payment_final": payment_final,
            "delivery_time_value": delivery_time_value,
            "delivery_time_unit": delivery_time_unit,
        }

        doc.render(context)

        # Guardar archivo generado
        output_filename = f"Cotizacion_{quote.client.full_name}_{quote.project_name}.docx"
        os.makedirs("generated_docs", exist_ok=True)
        output_path = os.path.join("generated_docs", output_filename)
        doc.save(output_path)

        # Devolver como descarga
        with open(output_path, "rb") as f:
            response = HttpResponse(
                f.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            response["Content-Disposition"] = f'attachment; filename="{output_filename}"'
            return response

    # Si es GET, mostrar página con los detalles
    notes_range = range(1, 11)
    return render(
        request,
        "quotes/quote_details.html",
        {"quote": quote, "notes_range": notes_range}
    )
