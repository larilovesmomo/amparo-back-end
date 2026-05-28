# api/admin.py
from django.contrib import admin
from .models import Paciente, Medicamento, Agendamento, RegistroMedicacao

admin.site.register(Paciente)

admin.site.register(Medicamento)
admin.site.register(Agendamento)
admin.site.register(RegistroMedicacao)