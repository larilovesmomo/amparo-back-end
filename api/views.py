from django.shortcuts import render
from django.db import transaction

from datetime import date, timedelta, datetime
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Paciente, Medicamento, Agendamento, RegistroMedicacao
from .serializers import PacienteSerializer, MedicamentoSerializer, AgendamentoSerializer, RegistroMedicacaoSerializer, PacienteCreateSerializer, MedicamentoComAgendamentoSerializer, RegistroMedicacaoCreateSerializer, RegistroMedicacaoUpdateSerializer

class PacienteViewSet(viewsets.ModelViewSet):
    serializer_class = PacienteSerializer
    
    def get_queryset(self):
        return Paciente.objects.filter(pk=self.request.user.pk)

    def get_serializer_class(self):
        if self.action == 'create':
            return PacienteCreateSerializer
        return PacienteSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    

class MedicamentoViewSet(viewsets.ModelViewSet):
    serializer_class = MedicamentoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Retorna medicamentos do usuário logado.

        Por padrão, apenas os ativos. Passando ?include_inactive=true,
        retorna ativos e inativos.
        """
        queryset = Medicamento.objects.filter(paciente=self.request.user).order_by('-nome')
        if self.request.query_params.get('include_inactive') != 'true':
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return MedicamentoComAgendamentoSerializer
        
        return self.serializer_class

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data

            medicamento_inativo = Medicamento.objects.filter(
                paciente=request.user,
                nome=validated_data['nome'],
                is_active=False
            ).first()

            medicamento_ativo = Medicamento.objects.filter(
                paciente=request.user,
                nome=validated_data['nome'],
                is_active=True
            ).first()

            if medicamento_ativo:
                medicamento = medicamento_ativo
            elif medicamento_inativo:
                medicamento = medicamento_inativo
                medicamento.is_active = True
                medicamento.dosagem_valor = validated_data.get('dosagem_valor')
                medicamento.dosagem_unidade = validated_data.get('dosagem_unidade', 'mg')
                medicamento.observacao = validated_data.get('observacao', '')
                medicamento.estoque_atual = validated_data.get('estoque_atual', 0)
                medicamento.aviso_estoque_minimo = validated_data.get('aviso_estoque_minimo', 5)
                medicamento.save()
            else:
                medicamento = Medicamento.objects.create(
                    paciente=request.user,
                    nome=validated_data['nome'],
                    dosagem_valor=validated_data.get('dosagem_valor'),
                    dosagem_unidade=validated_data.get('dosagem_unidade', 'mg'),
                    observacao=validated_data.get('observacao', ''),
                    estoque_atual=validated_data.get('estoque_atual', 0),
                    aviso_estoque_minimo=validated_data.get('aviso_estoque_minimo', 5)
                )

            if medicamento_ativo:
                agendamentos = Agendamento.objects.filter(medicamento=medicamento)
                agendamentos_data = AgendamentoSerializer(agendamentos, many=True).data
                medicamento_data = MedicamentoSerializer(medicamento).data
                return Response({
                    "medicamento": medicamento_data,
                    "agendamentos": agendamentos_data
                }, status=status.HTTP_200_OK)

            data_fim_tratamento = None
            if validated_data.get('duracao_valor'):
                data_fim_tratamento = date.today() + timedelta(days=validated_data['duracao_valor'])

            horario_inicio_time = validated_data['horario_inicio']
            horario_fim_time = validated_data.get('horario_fim') 
            intervalo_horas = validated_data['intervalo']

            horario_atual_dt = datetime.combine(date.today(), horario_inicio_time)
            
            limite_do_dia_dt = datetime.combine(date.today(), horario_fim_time) if horario_fim_time else datetime.combine(date.today(), datetime.max.time())

            agendamentos_criados = []
            
            while horario_atual_dt <= limite_do_dia_dt:
                agendamento = Agendamento.objects.create(
                    paciente=request.user,
                    medicamento=medicamento,
                    horario=horario_atual_dt.time(),
                    frequencia='Diário',
                    data_fim=data_fim_tratamento
                )
                agendamentos_criados.append(agendamento)
                
                horario_atual_dt += timedelta(hours=intervalo_horas)
                
                if len(agendamentos_criados) >= (24 // intervalo_horas) + 1:
                    break
            
            agendamentos_data = AgendamentoSerializer(agendamentos_criados, many=True).data
            medicamento_data = MedicamentoSerializer(medicamento).data
            
            return Response({
                "medicamento": medicamento_data,
                "agendamentos": agendamentos_data
            }, status=status.HTTP_201_CREATED)
        
    def update(self, request, *args, **kwargs):
        serializer = MedicamentoComAgendamentoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        
        medicamento = self.get_object()
        
        medicamento.nome = validated_data['nome']
        medicamento.dosagem_valor = validated_data.get('dosagem_valor')
        medicamento.dosagem_unidade = validated_data.get('dosagem_unidade')
        medicamento.observacao = validated_data.get('observacao', '')
        if 'estoque_atual' in validated_data:
            medicamento.estoque_atual = validated_data['estoque_atual']
        if 'aviso_estoque_minimo' in validated_data:
            medicamento.aviso_estoque_minimo = validated_data['aviso_estoque_minimo']
        medicamento.save()
        
        medicamento.agendamentos.all().delete()
        
        data_fim_tratamento = None
        if validated_data.get('duracao_valor'):
            data_fim_tratamento = medicamento.created_at.date() + timedelta(days=validated_data['duracao_valor'])


        horario_inicio_time = validated_data['horario_inicio']
        horario_fim_time = validated_data.get('horario_fim') 
        intervalo_horas = validated_data['intervalo']

        horario_atual_dt = datetime.combine(date.today(), horario_inicio_time)
        
        limite_do_dia_dt = datetime.combine(date.today(), horario_fim_time) if horario_fim_time else datetime.combine(date.today(), datetime.max.time())

        agendamentos_criados = []
        
        while horario_atual_dt <= limite_do_dia_dt:
            agendamento = Agendamento.objects.create(
                paciente=request.user,
                medicamento=medicamento,
                horario=horario_atual_dt.time(),
                frequencia='Diário',
                data_fim=data_fim_tratamento
            )
            agendamentos_criados.append(agendamento)
            
            horario_atual_dt += timedelta(hours=intervalo_horas)
            
            if len(agendamentos_criados) >= (24 // intervalo_horas) + 1:
                break
        
        agendamentos_data = AgendamentoSerializer(agendamentos_criados, many=True).data
        medicamento_data = MedicamentoSerializer(medicamento).data
        
        return Response({
            "medicamento": medicamento_data,
            "agendamentos": agendamentos_data
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], url_path='inativar')
    def inativar(self, request, *args, **kwargs):
        try:
            medicamento = Medicamento.objects.get(
                pk=kwargs['pk'],
                paciente=request.user
            )
        except Medicamento.DoesNotExist:
            return Response(
                {"detail": "Medicamento não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        medicamento.is_active = False
        medicamento.save()

        return Response({
            "detail": "Medicamento inativado com sucesso.",
            "medicamento": MedicamentoSerializer(medicamento).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reativar')
    def reativar(self, request, *args, **kwargs):
        try:
            medicamento = Medicamento.objects.get(
                pk=kwargs['pk'],
                paciente=request.user
            )
        except Medicamento.DoesNotExist:
            return Response(
                {"detail": "Medicamento não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        medicamento.is_active = True
        medicamento.save()

        return Response({
            "detail": "Medicamento reativado com sucesso.",
            "medicamento": MedicamentoSerializer(medicamento).data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        medicamento = self.get_object()
        medicamento.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)

class AgendamentoViewSet(viewsets.ModelViewSet):
    serializer_class = AgendamentoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Agendamento.objects.filter(paciente=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(paciente=self.request.user)
        
# class RegistroMedicacaoViewSet(viewsets.ModelViewSet):
#     serializer_class = RegistroMedicacaoSerializer
#     permission_classes = [permissions.IsAuthenticated]
    
#     def get_queryset(self):
#         return RegistroMedicacao.objects.filter(paciente=self.request.user).order_by('-created_at')

#     def perform_create(self, serializer):
#         serializer.save(paciente=self.request.user)
        
class RegistroMedicacaoViewSet(viewsets.ModelViewSet):
    queryset = RegistroMedicacao.objects.all().order_by('-data_hora_tomada')
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        
        if self.action == 'create':
            return RegistroMedicacaoCreateSerializer
       
        if self.action in ['update', 'partial_update']:
            return RegistroMedicacaoUpdateSerializer
        
        return RegistroMedicacaoSerializer
    
    def get_queryset(self):
        return self.queryset.filter(paciente=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(paciente=self.request.user)
        
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        read_serializer = RegistroMedicacaoSerializer(instance)
        return Response(read_serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        read_serializer = RegistroMedicacaoSerializer(instance)
        return Response(read_serializer.data)
