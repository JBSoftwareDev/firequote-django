from docxtpl import DocxTemplate

def generate_doc(template_path, context, output_path):
    doc = DocxTemplate(template_path)
    doc.render(context)
    doc.save(output_path)