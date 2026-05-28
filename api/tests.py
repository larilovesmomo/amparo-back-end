# api/tests.py
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Medicamento, Agendamento

Paciente = get_user_model()

class MedicamentoIntegrationTest(APITestCase):
    
    def setUp(self):
        
        self.user = Paciente.objects.create_user(username='testuser', password='testpassword123')
        self.client.force_authenticate(user=self.user)

    def test_create_medication_and_schedules(self):
        payload = {
            "nome": "Ibuprofeno",
            "dosagem_valor": "600.00",
            "dosagem_unidade": "mg",
            "horario_inicio": "08:00:00",
            "intervalo": 8,
            "duracao_valor": 7,
            "duracao_unidade": "dias",
            "observacao": "Tomar após as refeições",
            "estoque_atual": 20,
            "aviso_estoque_minimo": 5
        }

        response = self.client.post('/api/medicamentos/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Medicamento.objects.count(), 1)
        
        self.assertEqual(Medicamento.objects.get().nome, 'Ibuprofeno')

        self.assertEqual(Agendamento.objects.count(), 2)
        
        horarios_criados = [ag.horario.strftime('%H:%M:%S') for ag in Agendamento.objects.all()]
        self.assertIn('08:00:00', horarios_criados)
        self.assertIn('16:00:00', horarios_criados)
        
        primeiro_agendamento = Agendamento.objects.first()
        self.assertEqual(primeiro_agendamento.medicamento.nome, 'Ibuprofeno')