# load_templates.py
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "firequote.settings")
django.setup()

from django.core.files import File
from quotes.models import TemplateDoc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "quotes", "templates_docs")

def infer_tags_from_name(fname):
    # fname sin .docx, p.ej 'detection_protection_both'
    base = fname.replace(".docx","")
    parts = base.split("_")
    if not parts:
        return "", ""
    fmt = parts[-1]  # autocad, revit, both
    services = parts[:-1]
    services_tag = "|".join(services)
    formats_tag = fmt
    return services_tag, formats_tag

def main():
    files = [f for f in os.listdir(templates_dir) if f.lower().endswith(".docx")]
    print(f"Found {len(files)} templates in {templates_dir}")
    for f in files:
        fullpath = os.path.join(templates_dir, f)
        services_tag, formats_tag = infer_tags_from_name(f)
        name = f  # puedes usar el mismo nombre como display name
        # Busca registro existente por name
        obj = TemplateDoc.objects.filter(name=name).first()
        if obj:
            print(f"Updating {name} (services={services_tag}, formats={formats_tag})")
            # reemplazar archivo
            with open(fullpath, "rb") as fp:
                django_file = File(fp)
                obj.file.save(f, django_file, save=True)
            obj.services_tag = services_tag
            obj.formats_tag = formats_tag
            obj.save()
        else:
            print(f"Creating {name} (services={services_tag}, formats={formats_tag})")
            with open(fullpath, "rb") as fp:
                django_file = File(fp)
                obj = TemplateDoc.objects.create(
                    name=name,
                    file=None,
                    services_tag=services_tag,
                    formats_tag=formats_tag,
                )
                obj.file.save(f, django_file, save=True)
    print("Done.")

if __name__ == "__main__":
    main()
