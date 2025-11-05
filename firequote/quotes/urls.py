from django.urls import path
from . import views

urlpatterns = [
    path('', views.quote_form, name='quote_form'),
    path('quote/<int:quote_id>/', views.quote_details, name='quote_details'),
]
