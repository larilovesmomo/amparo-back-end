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


class MedicamentoInativacaoTest(APITestCase):

    def setUp(self):
        self.user = Paciente.objects.create_user(username='testuser', password='testpassword123')
        self.client.force_authenticate(user=self.user)
        self.medicamento = Medicamento.objects.create(
            paciente=self.user,
            nome='Ibuprofeno',
            dosagem_valor=Decimal('600.00'),
            dosagem_unidade='mg',
            estoque_atual=Decimal('20.00'),
        )
        self.agendamento = Agendamento.objects.create(
            paciente=self.user,
            medicamento=self.medicamento,
            horario='08:00:00',
            frequencia='Diário',
        )
        self.registro = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento,
            data_hora_tomada=timezone.now(),
            tomou=True,
        )

    def test_01_inativacao_preserva_historico(self):
        """Inativação preserva Medicamento, Agendamento e RegistroMedicacao."""
        response = self.client.post(f'/api/medicamentos/{self.medicamento.pk}/inativar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.medicamento.refresh_from_db()
        self.assertFalse(self.medicamento.is_active)

        self.assertTrue(Agendamento.objects.filter(pk=self.agendamento.pk).exists())
        self.assertTrue(RegistroMedicacao.objects.filter(pk=self.registro.pk).exists())
        self.assertTrue(Medicamento.objects.filter(pk=self.medicamento.pk).exists())

    def test_02_inativo_nao_aparece_listagem(self):
        """Medicamento inativo não aparece na listagem de medicamentos ativos."""
        response = self.client.post(f'/api/medicamentos/{self.medicamento.pk}/inativar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get('/api/medicamentos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_03_inativo_nao_gera_novas_acoes(self):
        """Medicamento inativo: agendamentos existentes permanecem mas não são recriados."""
        self.client.post(f'/api/medicamentos/{self.medicamento.pk}/inativar/')

        self.medicamento.refresh_from_db()
        self.assertFalse(self.medicamento.is_active)
        agendamentos = Agendamento.objects.filter(medicamento=self.medicamento)
        self.assertEqual(agendamentos.count(), 1)

    def test_04_reativacao_restaura_funcionamento(self):
        """Reativação restaura o medicamento para listagem e funcionalidade normal."""
        self.client.post(f'/api/medicamentos/{self.medicamento.pk}/inativar/')
        self.medicamento.refresh_from_db()
        self.assertFalse(self.medicamento.is_active)

        response = self.client.post(f'/api/medicamentos/{self.medicamento.pk}/reativar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.medicamento.refresh_from_db()
        self.assertTrue(self.medicamento.is_active)

        response = self.client.get('/api/medicamentos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['nome'], 'Ibuprofeno')

    def test_05_cadastro_inativo_reativa_sem_duplicar(self):
        """Cadastro de medicamento com mesmo nome de inativo reativa ao invés de duplicar."""
        self.client.post(f'/api/medicamentos/{self.medicamento.pk}/inativar/')
        self.medicamento.refresh_from_db()
        self.assertFalse(self.medicamento.is_active)
        self.assertEqual(Medicamento.objects.filter(paciente=self.user, nome='Ibuprofeno').count(), 1)

        payload = {
            "nome": "Ibuprofeno",
            "dosagem_valor": "500.00",
            "dosagem_unidade": "mg",
            "horario_inicio": "08:00:00",
            "intervalo": 8,
            "estoque_atual": 30,
            "aviso_estoque_minimo": 5,
        }
        response = self.client.post('/api/medicamentos/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Medicamento.objects.filter(paciente=self.user, nome='Ibuprofeno').count(), 1)
        self.medicamento.refresh_from_db()
        self.assertTrue(self.medicamento.is_active)
        self.assertEqual(self.medicamento.dosagem_valor, Decimal('500.00'))

    def test_06_exclusao_definitiva_continua_funcionando(self):
        """DELETE continua excluindo definitivamente o medicamento."""
        response = self.client.delete(f'/api/medicamentos/{self.medicamento.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Medicamento.objects.filter(pk=self.medicamento.pk).exists())

    def test_07_medicamentos_ativos_funcionam_normalmente(self):
        """Medicamentos ativos continuam aparecendo na listagem e funcionando normalmente."""
        response = self.client.get('/api/medicamentos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['nome'], 'Ibuprofeno')
        self.assertTrue(response.data[0]['is_active'])

        payload = {
            "nome": "Paracetamol",
            "dosagem_valor": "750.00",
            "dosagem_unidade": "mg",
            "horario_inicio": "08:00:00",
            "intervalo": 6,
            "estoque_atual": 10,
            "aviso_estoque_minimo": 3,
        }
        response = self.client.post('/api/medicamentos/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get('/api/medicamentos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_inativar_medico_inexistente(self):
        """Inativar medicamento inexistente retorna 404."""
        response = self.client.post('/api/medicamentos/9999/inativar/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reativar_medico_inexistente(self):
        """Reativar medicamento inexistente retorna 404."""
        response = self.client.post('/api/medicamentos/9999/reativar/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RegistroMedicacaoIsAtivoTest(APITestCase):
    """Testes de impedimento de registro de dose para medicamento inativo."""

    def setUp(self):
        self.user = Paciente.objects.create_user(username='testuser', password='testpassword123')
        self.other_user = Paciente.objects.create_user(username='otheruser', password='otherpassword123')
        self.client.force_authenticate(user=self.user)

        self.medicamento_ativo = Medicamento.objects.create(
            paciente=self.user,
            nome='Ibuprofeno',
            dosagem_valor=Decimal('600.00'),
            dosagem_unidade='mg',
            estoque_atual=Decimal('20.00'),
            is_active=True,
        )
        self.agendamento_ativo = Agendamento.objects.create(
            paciente=self.user,
            medicamento=self.medicamento_ativo,
            horario='08:00:00',
            frequencia='Diário',
        )

        self.medicamento_inativo = Medicamento.objects.create(
            paciente=self.user,
            nome='Amoxicilina',
            dosagem_valor=Decimal('500.00'),
            dosagem_unidade='mg',
            estoque_atual=Decimal('10.00'),
            is_active=False,
        )
        self.agendamento_inativo = Agendamento.objects.create(
            paciente=self.user,
            medicamento=self.medicamento_inativo,
            horario='08:00:00',
            frequencia='Diário',
        )

        self.other_medicamento = Medicamento.objects.create(
            paciente=self.other_user,
            nome='Outro Remedio',
            dosagem_valor=Decimal('200.00'),
            dosagem_unidade='mg',
            estoque_atual=Decimal('10.00'),
            is_active=True,
        )
        self.other_agendamento = Agendamento.objects.create(
            paciente=self.other_user,
            medicamento=self.other_medicamento,
            horario='09:00:00',
            frequencia='Diário',
        )

    def test_registro_para_medicamento_ativo_funciona(self):
        """Registro de dose para medicamento ativo continua funcionando."""
        payload = {
            'agendamento': self.agendamento_ativo.pk,
            'tomou': True,
            'data_hora_tomada': timezone.now().isoformat(),
        }
        response = self.client.post('/api/registros/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(RegistroMedicacao.objects.filter(agendamento=self.agendamento_ativo).exists())

    def test_registro_para_medicamento_inativo_e_rejeitado(self):
        """Registro de dose para medicamento inativo retorna erro 400."""
        payload = {
            'agendamento': self.agendamento_inativo.pk,
            'tomou': True,
            'data_hora_tomada': timezone.now().isoformat(),
        }
        response = self.client.post('/api/registros/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RegistroMedicacao.objects.filter(agendamento=self.agendamento_inativo).exists())

    def test_registros_historicos_preservados_apos_inativacao(self):
        """Registros existentes antes da inativação permanecem no banco."""
        reg = RegistroMedicacao.objects.create(
            paciente=self.user,
            agendamento=self.agendamento_inativo,
            data_hora_tomada=timezone.now(),
            tomou=True,
        )

        self.medicamento_inativo.is_active = False
        self.medicamento_inativo.save()

        self.assertTrue(RegistroMedicacao.objects.filter(pk=reg.pk).exists())

    def test_usuario_nao_pode_registrar_dose_de_outro_usuario(self):
        """Usuário não consegue registrar dose usando agendamento de outro usuário."""
        payload = {
            'agendamento': self.other_agendamento.pk,
            'tomou': True,
            'data_hora_tomada': timezone.now().isoformat(),
        }
        response = self.client.post('/api/registros/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(RegistroMedicacao.objects.filter(agendamento=self.other_agendamento).exists())

    def test_registro_para_medicamento_inativo_e_rejeitado_mesmo_apos_reativacao_temporaria(self):
        """Após reativação, registro volta a funcionar normalmente."""
        self.medicamento_inativo.is_active = True
        self.medicamento_inativo.save()

        payload = {
            'agendamento': self.agendamento_inativo.pk,
            'tomou': True,
            'data_hora_tomada': timezone.now().isoformat(),
        }
        response = self.client.post('/api/registros/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class MedicamentoDuplicacaoTest(APITestCase):
    """Testes de impedimento de duplicação de medicamento ativo com mesmo nome."""

    def setUp(self):
        self.user = Paciente.objects.create_user(username='testuser', password='testpassword123')
        self.client.force_authenticate(user=self.user)
        self.payload = {
            "nome": "Ibuprofeno",
            "dosagem_valor": "600.00",
            "dosagem_unidade": "mg",
            "horario_inicio": "08:00:00",
            "intervalo": 8,
            "estoque_atual": 20,
            "aviso_estoque_minimo": 5,
        }

    def test_criar_medicamento_inexistente_cria_apenas_um(self):
        """Cadastro de medicamento inexistente cria apenas um registro."""
        response = self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Medicamento.objects.filter(paciente=self.user).count(), 1)
        self.assertEqual(Agendamento.objects.filter(medicamento__paciente=self.user).count(), 2)

    def test_repetir_cadastro_mesmo_nome_nao_cria_outro(self):
        """Repetir cadastro de medicamento ativo com mesmo nome não cria outro registro."""
        self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(Medicamento.objects.filter(paciente=self.user, nome='Ibuprofeno').count(), 1)

        response = self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Medicamento.objects.filter(paciente=self.user, nome='Ibuprofeno').count(), 1)

    def test_retry_retorna_200_e_dados_existentes(self):
        """Retry retorna 200 OK e os dados do medicamento existente."""
        self.client.post('/api/medicamentos/', self.payload, format='json')
        medicamento_id = Medicamento.objects.get(paciente=self.user, nome='Ibuprofeno').pk

        response = self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['medicamento']['id'], medicamento_id)
        self.assertIn('agendamentos', response.data)
        self.assertEqual(len(response.data['agendamentos']), 2)

    def test_retry_nao_duplica_agendamentos(self):
        """Retry não cria novos agendamentos para o medicamento existente."""
        self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(Agendamento.objects.filter(medicamento__nome='Ibuprofeno').count(), 2)

        self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(Agendamento.objects.filter(medicamento__nome='Ibuprofeno').count(), 2)

    def test_reativar_inativo_continua_funcionando(self):
        """Cadastro de medicamento inativo com mesmo nome continua sendo reativado."""
        self.client.post('/api/medicamentos/', self.payload, format='json')
        medicamento = Medicamento.objects.get(paciente=self.user, nome='Ibuprofeno')
        self.client.post(f'/api/medicamentos/{medicamento.pk}/inativar/')
        medicamento.refresh_from_db()
        self.assertFalse(medicamento.is_active)

        response = self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        medicamento.refresh_from_db()
        self.assertTrue(medicamento.is_active)
        self.assertEqual(Medicamento.objects.filter(paciente=self.user, nome='Ibuprofeno').count(), 1)

    def test_nomes_diferentes_criam_medicamentos_separados(self):
        """Medicamentos com nomes diferentes são cadastrados normalmente."""
        self.client.post('/api/medicamentos/', self.payload, format='json')

        payload2 = {**self.payload, "nome": "Paracetamol"}
        response = self.client.post('/api/medicamentos/', payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Medicamento.objects.filter(paciente=self.user).count(), 2)

    def test_diferentes_usuarios_mesmo_nome(self):
        """Diferentes usuários podem ter medicamentos com o mesmo nome."""
        self.client.post('/api/medicamentos/', self.payload, format='json')

        other_user = Paciente.objects.create_user(username='other', password='pass123')
        self.client.force_authenticate(user=other_user)
        response = self.client.post('/api/medicamentos/', self.payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Medicamento.objects.filter(nome='Ibuprofeno').count(), 2)