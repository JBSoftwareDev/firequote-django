# convertir quotes_data.json a UTF-8 limpio
with open("quotes_data.json", "r", encoding="latin-1") as f:
    data = f.read()

with open("quotes_data.json", "w", encoding="utf-8") as f:
    f.write(data)

print("Archivo convertido a UTF-8 correctamente.")
