def format_currency(value):
    """
    Formats numbers Colombian style:
    1000000 → $1.000.000
    """
    try:
        value = float(value)
        return "$" + f"{value:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def calculate_prices(area_sqm, building_type, services, formats):
    """
    Calculates independent prices for:
    - AutoCAD
    - Revit
    - Combined total (sum, NOT multiplier)
    """

    price_table = {
        "commercial": {
            "detection": 1000,
            "protection": 1000,
            "human_safety": 500,
        },
        "residential": {
            "detection": 500,
            "protection": 500,
            "human_safety": 250,
        }
    }

    selected_prices = price_table.get(building_type, {})

    # -------------------------
    # BASE CALCULATION (per service)
    # -------------------------
    detection_base = selected_prices.get("detection", 0) * area_sqm if services.get("detection") else 0
    protection_base = selected_prices.get("protection", 0) * area_sqm if services.get("protection") else 0
    human_safety_base = selected_prices.get("human_safety", 0) * area_sqm if services.get("human_safety") else 0

    # -------------------------
    # AUTOCAD VALUES
    # -------------------------
    detection_autocad = detection_base if formats.get("autocad") else 0
    protection_autocad = protection_base if formats.get("autocad") else 0
    human_safety_autocad = human_safety_base if formats.get("autocad") else 0

    total_autocad = detection_autocad + protection_autocad + human_safety_autocad

    # -------------------------
    # REVIT VALUES (independent)
    # -------------------------
    detection_revit = detection_base if formats.get("revit") else 0
    protection_revit = protection_base if formats.get("revit") else 0
    human_safety_revit = human_safety_base if formats.get("revit") else 0

    total_revit = detection_revit + protection_revit + human_safety_revit

    # -------------------------
    # FINAL TOTAL (SUM, NOT MULTIPLY)
    # -------------------------
    grand_total = total_autocad + total_revit

    return {
        # AutoCAD
        "detection_autocad": detection_autocad,
        "protection_autocad": protection_autocad,
        "human_safety_autocad": human_safety_autocad,
        "total_autocad": total_autocad,

        # Revit
        "detection_revit": detection_revit,
        "protection_revit": protection_revit,
        "human_safety_revit": human_safety_revit,
        "total_revit": total_revit,

        # Combined
        "grand_total": grand_total,
    }

# Utility: converts multiline text input into a clean list of items
def parse_items(text):
    if not text:
        return []
    return [i.strip() for i in text.split("\n") if i.strip()]

from num2words import num2words

def build_payment_schedule(advance, first_version, final):
    """
    Genera:

    - Cuarenta (40%) Anticipo
    - Cuarenta (40%) Contra la entrega de la primera versión del diseño
    - Veinte (20%) Contra la entrega final del diseño
    """

    def porcentaje_texto(valor):
        try:
            valor = int(valor)
        except:
            valor = 0

        texto = num2words(valor, lang="es")

        return f"{texto.capitalize()} ({valor}%)"

    lineas = [
        f"{porcentaje_texto(advance)} Anticipo",
        f"{porcentaje_texto(first_version)} Contra la entrega de la primera versión del diseño",
        f"{porcentaje_texto(final)} Contra la entrega final del diseño",
    ]

    spacing = "\u00A0" * 5

    return "\n".join(f"-{spacing}{linea}" for linea in lineas)

def build_total_text(value):
    """
    Genera texto SIN IVA incluido.
    El texto + IVA sigue apareciendo solo como referencia.
    """

    try:
        value = float(value)
    except Exception:
        value = 0

    # Número sin IVA
    number_text = format_currency(value)

    # Convertir a letras SIN IVA
    words = num2words(value, lang="es")

    # Limpiar decimales
    words = (
        words
        .replace(" coma cero", "")
        .replace(" coma cero cero", "")
    )

    return (
        f"El valor total de la propuesta es de "
        f"({number_text} + IVA) "
        f"{words} pesos M.L. + IVA"
    )

def build_additional_notes(notes):
    """
    Genera variables independientes para Word.

    note_title_1
    note_title_2
    note_text_1
    ...
    """

    clean_notes = [
        n.strip()
        for n in notes
        if n and n.strip()
    ]

    result = {}

    # Inicializar vacías
    for i in range(1, 12):
        result[f"note_title_{i}"] = ""

    for i in range(1, 11):
        result[f"note_text_{i}"] = ""

    # SIN notas adicionales
    if not clean_notes:
        result["note_title_1"] = "Nota:"
        return result

    # CON notas adicionales
    result["note_title_1"] = "Nota 1:"

    for i, note in enumerate(clean_notes):

        if i >= 10:
            break

        result[f"note_title_{i + 2}"] = f"Nota {i + 2}:"
        result[f"note_text_{i + 1}"] = note

    return result

def get_template_filename(is_detection, is_protection, is_human_safety, deliver_autocad, deliver_revit):
    services = []

    if is_detection:
        services.append("detection")
    if is_protection:
        services.append("protection")
    if is_human_safety:
        services.append("human_safety")

    if deliver_autocad and deliver_revit:
        format_tag = "both"
    elif deliver_autocad:
        format_tag = "autocad"
    elif deliver_revit:
        format_tag = "revit"
    else:
        return None

    service_tag = "_".join(services)

    if not service_tag:
        return None

    return f"{service_tag}_{format_tag}.docx"

def build_output_filename(quote):
    project_name = (quote.project_name or "").upper().strip()

    is_detection = quote.is_detection
    is_protection = quote.is_protection
    is_human_safety = quote.is_human_safety

    # -------------------------
    # SINGLE SERVICE
    # -------------------------
    if is_human_safety and not is_detection and not is_protection:
        filename = f"COTIZACION DEL ANÁLISIS DE SEGURIDAD HUMANA - {project_name}.docx"

    elif is_detection and not is_protection and not is_human_safety:
        filename = f"COTIZACION DEL DISEÑO DE DETECCIÓN DE INCENDIOS - {project_name}.docx"

    elif is_protection and not is_detection and not is_human_safety:
        filename = f"COTIZACION DEL DISEÑO DE EXTINCIÓN DE INCENDIOS - {project_name}.docx"

    # -------------------------
    # TWO SERVICES
    # -------------------------
    elif is_detection and is_protection and not is_human_safety:
        filename = f"COTIZACION DE LOS DISEÑOS DE PROTECCIÓN CONTRA INCENDIOS - {project_name}.docx"

    elif is_human_safety and is_detection and not is_protection:
        filename = f"COTIZACION DE LOS DISEÑOS DE SEGURIDAD HUMANA Y DETECCIÓN DE INCENDIOS - {project_name}.docx"

    elif is_human_safety and is_protection and not is_detection:
        filename = f"COTIZACION DE LOS DISEÑOS DE SEGURIDAD HUMANA Y EXTINCIÓN DE INCENDIOS - {project_name}.docx"

    # -------------------------
    # THREE SERVICES
    # -------------------------
    elif is_human_safety and is_detection and is_protection:
        filename = f"COTIZACION DE LOS DISEÑOS DE SEGURIDAD HUMANA Y PROTECCIÓN CONTRA INCENDIOS - {project_name}.docx"

    else:
        filename = f"COTIZACION - {project_name}.docx"

    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']

    for char in invalid_chars:
        filename = filename.replace(char, "")

    return filename

from django.db import transaction
from django.utils import timezone
from quotes.models import QuoteCounter


def get_next_quote_number():
    current_year = timezone.now().year

    initial_number = 320 if current_year == 2026 else 1

    with transaction.atomic():
        counter, created = QuoteCounter.objects.select_for_update().get_or_create(
            year=current_year,
            defaults={"next_number": initial_number}
        )

        number = counter.next_number
        counter.next_number += 1
        counter.save()

    return current_year, number