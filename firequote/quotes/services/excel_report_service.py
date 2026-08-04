from collections import defaultdict
from copy import copy
from io import BytesIO
from pathlib import Path
from unicodedata import combining, normalize

from django.conf import settings
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font


TEMPLATE_SHEET_NAME = "2026"
HEADER_ROW = 10
DATA_START_ROW = 11


def normalize_header(value):
    """
    Convierte los encabezados a un formato comparable.

    Ejemplo:
    'Teléfono' -> 'TELEFONO'
    """
    if value is None:
        return ""

    text = str(value).strip().upper()
    text = normalize("NFKD", text)

    text = "".join(
        character
        for character in text
        if not combining(character)
    )

    return " ".join(text.split())


def get_header_columns(worksheet):
    """
    Devuelve las posiciones de las columnas según sus encabezados.

    Ejemplo:
    {
        "NUMERO": 2,
        "DESCRIPCION DE LA COTIZACION": 3,
        ...
    }
    """
    columns = {}

    for cell in worksheet[HEADER_ROW]:
        header = normalize_header(cell.value)

        if header:
            columns[header] = cell.column

    return columns


def find_column(header_columns, *possible_names):
    """
    Busca una columna aceptando diferentes variaciones del encabezado.
    """
    for name in possible_names:
        normalized_name = normalize_header(name)

        if normalized_name in header_columns:
            return header_columns[normalized_name]

    return None


def write_value(
    worksheet,
    row_number,
    header_columns,
    value,
    *possible_headers,
):
    column_number = find_column(
        header_columns,
        *possible_headers,
    )

    if column_number is None:
        return

    worksheet.cell(
        row=row_number,
        column=column_number,
        value=value,
    )


def copy_row_style(worksheet, source_row, target_row):
    """
    Copia el formato de la fila modelo a una fila nueva.
    """
    worksheet.row_dimensions[target_row].height = (
        worksheet.row_dimensions[source_row].height
    )

    for column_number in range(1, worksheet.max_column + 1):
        source_cell = worksheet.cell(
            row=source_row,
            column=column_number,
        )

        target_cell = worksheet.cell(
            row=target_row,
            column=column_number,
        )

        if source_cell.has_style:
            target_cell.font = copy(source_cell.font)
            target_cell.fill = copy(source_cell.fill)
            target_cell.border = copy(source_cell.border)
            target_cell.alignment = copy(source_cell.alignment)
            target_cell.number_format = source_cell.number_format
            target_cell.protection = copy(source_cell.protection)

        if source_cell.hyperlink:
            target_cell._hyperlink = copy(source_cell.hyperlink)

def apply_data_font(worksheet, row_number):
    """
    Aplica a las celdas de datos la fuente utilizada
    tradicionalmente en el archivo de seguimiento.
    """
    for column_number in range(1, worksheet.max_column + 1):
        cell = worksheet.cell(
            row=row_number,
            column=column_number,
        )

        if isinstance(cell, MergedCell):
            continue

        cell.font = Font(
            name="Cambria",
            size=11,
            bold=False,
            italic=False,
        )

def clear_data_area(worksheet):
    """
    Borra los valores de la zona de datos sin modificar
    las celdas secundarias que forman parte de rangos combinados.
    """
    for row in worksheet.iter_rows(
        min_row=DATA_START_ROW,
        max_row=worksheet.max_row,
    ):
        for cell in row:
            if isinstance(cell, MergedCell):
                continue

            cell.value = None


def update_sheet_title(worksheet, year):
    """
    Cambia el título grande de la hoja al año correspondiente.

    Busca cualquier celda que contenga:
    SEGUIMIENTO A COTIZACIONES
    """
    for row in worksheet.iter_rows(
        min_row=1,
        max_row=HEADER_ROW - 1,
    ):
        for cell in row:
            if not isinstance(cell.value, str):
                continue

            if "SEGUIMIENTO A COTIZACIONES" in cell.value.upper():
                cell.value = f"SEGUIMIENTO A COTIZACIONES - {year}"
                return


def copy_images(source_worksheet, target_worksheet):
    """
    copy_worksheet() no copia imágenes.

    Esta función copia el logotipo y cualquier otra imagen
    existente en la hoja modelo.
    """
    for image in getattr(source_worksheet, "_images", []):
        copied_image = copy(image)
        copied_image.anchor = copy(image.anchor)
        target_worksheet.add_image(copied_image)


def copy_auto_filter(source_worksheet, target_worksheet):
    """
    Copia el rango del filtro de la hoja modelo.
    """
    if source_worksheet.auto_filter.ref:
        target_worksheet.auto_filter.ref = (
            source_worksheet.auto_filter.ref
        )


def copy_print_settings(source_worksheet, target_worksheet):
    """
    Copia configuraciones importantes de impresión.
    """
    target_worksheet.freeze_panes = source_worksheet.freeze_panes
    target_worksheet.sheet_view.showGridLines = (
        source_worksheet.sheet_view.showGridLines
    )

    target_worksheet.page_margins = copy(
        source_worksheet.page_margins
    )

    target_worksheet.page_setup = copy(
        source_worksheet.page_setup
    )

    target_worksheet.print_options = copy(
        source_worksheet.print_options
    )

    target_worksheet.sheet_properties = copy(
        source_worksheet.sheet_properties
    )

    target_worksheet.print_title_rows = (
        source_worksheet.print_title_rows
    )

    target_worksheet.print_title_cols = (
        source_worksheet.print_title_cols
    )

    if source_worksheet.print_area:
        target_worksheet.print_area = (
            source_worksheet.print_area
        )


def create_year_sheet(workbook, template_worksheet, year):
    """
    Crea una copia de la hoja 2026 para un año posterior.
    """
    target_worksheet = workbook.copy_worksheet(
        template_worksheet
    )

    target_worksheet.title = str(year)

    # Las imágenes no son copiadas por copy_worksheet.
    copy_images(
        source_worksheet=template_worksheet,
        target_worksheet=target_worksheet,
    )

    copy_auto_filter(
        source_worksheet=template_worksheet,
        target_worksheet=target_worksheet,
    )

    copy_print_settings(
        source_worksheet=template_worksheet,
        target_worksheet=target_worksheet,
    )

    update_sheet_title(
        worksheet=target_worksheet,
        year=year,
    )

    clear_data_area(target_worksheet)

    return target_worksheet


def get_quote_year(quote):
    """
    Obtiene el año real de la cotización.

    Primero intenta usar quote_year, si existe.
    De lo contrario usa created_at.
    """
    quote_year = getattr(quote, "quote_year", None)

    if quote_year:
        try:
            return int(quote_year)
        except (TypeError, ValueError):
            pass

    if quote.created_at:
        return quote.created_at.year

    return None


def get_quote_number(quote, fallback_number):
    """
    Devuelve solamente la parte numérica.

    Ejemplos:
    COT320-26 -> 320
    COT321-26 -> 321

    Las cotizaciones históricas que no tengan quote_number
    reciben su posición consecutiva dentro de la hoja.
    """
    stored_number = getattr(quote, "quote_number", None)

    if stored_number not in (None, ""):
        try:
            return int(stored_number)
        except (TypeError, ValueError):
            pass

    return fallback_number


def get_quote_description(quote):
    """
    Texto para la columna Descripción de la cotización.

    Actualmente usa el nombre del proyecto.
    """
    return quote.project_name or ""


def get_client_company(quote):
    """
    Texto para la columna Cliente.
    """
    return quote.client.company or ""


def get_quote_value(quote):
    """
    Valor sin IVA.

    Usa total_value porque ese es el total guardado actualmente
    en el modelo Quote.
    """
    return quote.total_value or 0


def get_approved_text(quote):
    """
    Intenta detectar un campo de aprobación si existe.

    Si el modelo no tiene ese campo, deja la columna vacía.
    """
    possible_fields = (
        "is_approved",
        "approved",
        "aprobado",
    )

    for field_name in possible_fields:
        if hasattr(quote, field_name):
            value = getattr(quote, field_name)

            if value is True:
                return "Sí"

            if value is False:
                return "No"

            if value not in (None, ""):
                return str(value)

    return ""


def validate_template_headers(worksheet):
    """
    Comprueba que los encabezados indispensables existan.
    """
    header_columns = get_header_columns(worksheet)

    required_headers = {
        "Número de cotización": (
            "Número de cotización",
            "Numero de cotizacion",
            "Número",
            "Numero",
        ),
        "Descripción de la cotización": (
            "Descripción de la cotización",
            "Descripcion de la cotizacion",
        ),
        "Cliente": (
            "Cliente",
        ),
        "Valor sin IVA": (
            "Valor sin IVA",
        ),
        "Fecha de cotización": (
            "Fecha de cotización",
            "Fecha de cotizacion",
            "Fecha cotización",
            "Fecha cotizacion",
        ),
    }

    missing_headers = []

    for display_name, possible_names in required_headers.items():
        if find_column(
            header_columns,
            *possible_names,
        ) is None:
            missing_headers.append(display_name)

    if missing_headers:
        missing_text = ", ".join(missing_headers)

        raise ValueError(
            "La plantilla no contiene los siguientes encabezados "
            f"en la fila {HEADER_ROW}: {missing_text}."
        )


def fill_year_sheet(worksheet, quotes):
    """
    Llena una hoja con las cotizaciones de un año.
    """
    clear_data_area(worksheet)

    header_columns = get_header_columns(worksheet)

    for index, quote in enumerate(quotes):
        target_row = DATA_START_ROW + index

        # Si se supera el número de filas ya formateadas,
        # copia la fila modelo.
        if target_row != DATA_START_ROW:
            copy_row_style(
                worksheet=worksheet,
                source_row=DATA_START_ROW,
                target_row=target_row,
            )

        write_value(
            worksheet,
            target_row,
            header_columns,
            get_quote_number(
                quote=quote,
                fallback_number=index + 1,
            ),
            "Número de cotización",
            "Numero de cotizacion",
            "Número",
            "Numero",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            get_quote_description(quote),
            "Descripción de la cotización",
            "Descripcion de la cotizacion",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            get_client_company(quote),
            "Cliente",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            get_quote_value(quote),
            "Valor sin IVA",
        )

        quote_date = (
            quote.created_at.date()
            if quote.created_at
            else None
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            quote_date,
            "Fecha de cotización",
            "Fecha de cotizacion",
            "Fecha cotización",
            "Fecha cotizacion",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            get_approved_text(quote),
            "Aprobado",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            quote.client.phone or "",
            "Teléfono",
            "Telefono",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            quote.client.full_name or "",
            "Persona Encargada",
            "Persona encargada",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            quote.client.position or "",
            "Cargo",
        )

        write_value(
            worksheet,
            target_row,
            header_columns,
            quote.client.email or "",
            "Correo",
            "Email",
        )

        date_column = find_column(
            header_columns,
            "Fecha de cotización",
            "Fecha de cotizacion",
            "Fecha cotización",
            "Fecha cotizacion",
        )

        if date_column:
            worksheet.cell(
                row=target_row,
                column=date_column,
            ).number_format = "dd/mm/yyyy"

        value_column = find_column(
            header_columns,
            "Valor sin IVA",
        )

        if value_column:
            worksheet.cell(
                row=target_row,
                column=value_column,
            ).number_format = '$#,##0'

        apply_data_font(
            worksheet=worksheet,
            row_number=target_row,
        )


def generate_quotes_excel_report(quotes):
    """
    Genera el reporte completo:

    - conserva las hojas 2018-2025;
    - llena la hoja 2026;
    - crea 2027, 2028, etc., cuando existan cotizaciones;
    - conserva las demás hojas del archivo.
    """
    template_path = Path(
        settings.BASE_DIR,
        "quotes",
        "excel_templates",
        "seguimiento_cotizaciones_template.xlsx",
    )

    if not template_path.exists():
        raise FileNotFoundError(
            "No se encontró la plantilla Excel en: "
            f"{template_path}"
        )

    workbook = load_workbook(template_path)

    if TEMPLATE_SHEET_NAME not in workbook.sheetnames:
        raise ValueError(
            "La plantilla debe contener una hoja llamada "
            f"'{TEMPLATE_SHEET_NAME}'."
        )

    template_worksheet = workbook[TEMPLATE_SHEET_NAME]

    validate_template_headers(template_worksheet)

    quotes_by_year = defaultdict(list)

    for quote in quotes:
        year = get_quote_year(quote)

        if year is None:
            continue

        # Las hojas históricas 2018-2025 se conservan como están.
        if year >= 2026:
            quotes_by_year[year].append(quote)

    # La hoja 2026 siempre existe, aunque no haya cotizaciones.
    update_sheet_title(
        worksheet=template_worksheet,
        year=2026,
    )

    fill_year_sheet(
        worksheet=template_worksheet,
        quotes=quotes_by_year.get(2026, []),
    )

    # Crea únicamente los años posteriores que tengan registros.
    future_years = sorted(
        year
        for year in quotes_by_year
        if year > 2026
    )

    for year in future_years:
        sheet_name = str(year)

        if sheet_name in workbook.sheetnames:
            year_worksheet = workbook[sheet_name]
            clear_data_area(year_worksheet)
            update_sheet_title(year_worksheet, year)
        else:
            year_worksheet = create_year_sheet(
                workbook=workbook,
                template_worksheet=template_worksheet,
                year=year,
            )

        fill_year_sheet(
            worksheet=year_worksheet,
            quotes=quotes_by_year[year],
        )

    output = BytesIO()

    workbook.save(output)
    output.seek(0)

    return output