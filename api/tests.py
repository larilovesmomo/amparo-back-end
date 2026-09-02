# api/tests.py
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from .models import Medicamento, Agendamento, RegistroMedicacao

Paciente = get_user_model()

class RegistroMedicacaoEstoqueTest(APITestCase):
    """Testes de correção do BUG 06: inflação de estoque ao desfazer dose."""

    def setUp(self):
        self.user = Paciente.objects.create_user(username='testuser', password='testpassword123')
        self.medicamento = Medicamento.objects.create(
            paciente=self.user,
            nome='Ibuprofeno',
            dosagem_valor=Decimal('10.00'),
            dosagem_unidade='comprimido(s)',
            estoque_atual=Decimal('20.00'),
        )
        self.agendamento = Agendamento.objects.create(
            paciente=self.user,
            medicamento=self.medicamento,
            horario='08:00:00',
            frequencia='Diário',
        )

    def test_estoque_maior_que_dosagem(self):
        """Estoque 20 / dose 10 → tomar = 10, desfazer = 20."""
        self.assertEqual(self.medicamento.estoque_atual, Decimal('20.00'))

        reg = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento,
            data_hora_tomada=timezone.now(),
            tomou=True,
        )
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('10.00'))

        reg.tomou = False
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('20.00'))

    def test_estoque_menor_que_dosagem(self):
        """Estoque 5 / dose 10 → tomar = 0, desfazer = 5."""
        self.medicamento.estoque_atual = Decimal('5.00')
        self.medicamento.save()

        reg = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento,
            data_hora_tomada=timezone.now(),
            tomou=True,
        )
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('0.00'))

        reg.tomou = False
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('5.00'))

    def test_estoque_zero(self):
        """Estoque 0 / dose 10 → tomar = 0, desfazer = 0."""
        self.medicamento.estoque_atual = Decimal('0.00')
        self.medicamento.save()

        reg = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento,
            data_hora_tomada=timezone.now(),
            tomou=True,
        )
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('0.00'))

        reg.tomou = False
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('0.00'))

    def test_ciclo_completo_false_true_false_true_false(self):
        """false → true → false → true → false, estoque não inflaciona nem desconta duas vezes."""
        self.medicamento.estoque_atual = Decimal('5.00')
        self.medicamento.save()

        reg = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento,
            data_hora_tomada=timezone.now(),
            tomou=False,
        )
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('5.00'))

        reg.tomou = True
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('0.00'))

        reg.tomou = False
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('5.00'))

        reg.tomou = True
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('0.00'))

        reg.tomou = False
        reg.save()
        self.medicamento.refresh_from_db()
        self.assertEqual(self.medicamento.estoque_atual, Decimal('5.00'))


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