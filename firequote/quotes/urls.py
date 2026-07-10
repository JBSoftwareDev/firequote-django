from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path("cotizaciones/nueva/", views.quote_form, name="quote_form"),
    path("quote/<int:quote_id>/", views.quote_details, name="quote_details"),

    path("clientes/", views.client_list, name="client_list"),
    path("clientes/<int:client_id>/", views.client_detail, name="client_detail"),
    path("clientes/<int:client_id>/editar/", views.client_update, name="client_update"),
    path("clientes/<int:client_id>/eliminar/", views.client_delete, name="client_delete"),

    path("cotizaciones/", views.quote_list, name="quote_list"),
    path("cotizaciones/<int:quote_id>/detalle/", views.quote_info, name="quote_info"),
    path("cotizaciones/<int:quote_id>/eliminar/", views.quote_delete, name="quote_delete"),
    path(
        "backup/download/",
        views.download_backup,
        name="download_backup",
    ),
]