# quotes/admin.py
from django.contrib import admin
from .models import Client, Norm, TemplateDoc, Quote

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company', 'city', 'created_at')
    search_fields = ('full_name', 'company', 'city')

@admin.register(Norm)
class NormAdmin(admin.ModelAdmin):
    list_display = ('code', 'is_default', 'description')
    search_fields = ('code',)

@admin.register(TemplateDoc)
class TemplateDocAdmin(admin.ModelAdmin):
    list_display = ('name', 'services_tag', 'formats_tag')
    search_fields = ('name',)

@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('project_name', 'client', 'created_at', 'total_value')
    list_filter = ('is_detection', 'is_protection', 'is_human_safety')
    search_fields = ('project_name', 'client__full_name', 'client__company')
