# api/serializers.py

from rest_framework import serializers
from .models import Paciente, Medicamento, Agendamento, RegistroMedicacao
from datetime import date

class PacienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paciente
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        
class PacienteCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = Paciente
        fields = ['username', 'password']
    
    def create(self, validated_data):
        username = validated_data['username']
        placeholder_email = f"{username.lower()}@amparo.app"
        if Paciente.objects.filter(email=placeholder_email).exists():
            raise serializers.ValidationError({"error": "Um erro inesperado ocorreu. Tente um nome de usuário diferente."})
        
        user = Paciente.objects.create_user(
            username=username,
            password=validated_data['password'],
            email=placeholder_email 
        )
        return user
    
class AgendamentoSimplesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agendamento
        fields = ['id', 'horario', 'frequencia', 'data_fim']

class MedicamentoSerializer(serializers.ModelSerializer):
    horario_inicio = serializers.SerializerMethodField()
    horario_fim = serializers.SerializerMethodField()
    intervalo = serializers.SerializerMethodField()
    duracao_valor = serializers.SerializerMethodField()

    class Meta:
        model = Medicamento
        fields = [
            'id', 'nome', 'dosagem_valor', 'dosagem_unidade', 'observacao', 
            'estoque_atual', 'aviso_estoque_minimo', 'is_active',
            'horario_inicio', 'horario_fim', 'intervalo', 'duracao_valor'
        ]

    def get_horario_inicio(self, obj):
        primeiro = obj.agendamentos.order_by('horario').first()
        return primeiro.horario.strftime('%H:%M:%S') if primeiro else None

    def get_horario_fim(self, obj):
        if obj.agendamentos.count() > 1:
            ultimo = obj.agendamentos.order_by('horario').last()
            return ultimo.horario.strftime('%H:%M:%S') if ultimo else None
        return None

    def get_intervalo(self, obj):
        agendamentos = list(obj.agendamentos.order_by('horario'))
        if len(agendamentos) > 1:
            h1 = agendamentos[0].horario
            h2 = agendamentos[1].horario
            return h2.hour - h1.hour
        elif len(agendamentos) == 1:
            return 24  
        return None

    def get_duracao_valor(self, obj):
        agendamento = obj.agendamentos.first()
        if agendamento and agendamento.data_fim:
            delta = agendamento.data_fim - date.today()
            return max(0, delta.days)
        return None

class AgendamentoSerializer(serializers.ModelSerializer):
    paciente = PacienteSerializer(read_only=True)
    medicamento = MedicamentoSerializer(read_only=True)
    
    class Meta:
        model = Agendamento
        fields = ['id', 'horario', 'frequencia', 'paciente', 'medicamento', 'data_fim']
        
        
class RegistroMedicacaoSerializer(serializers.ModelSerializer):
    agendamento = AgendamentoSerializer(read_only=True)
    
    class Meta:
        model = RegistroMedicacao
        fields = ['id', 'data_hora_tomada', 'tomou', 'agendamento']
        
class RegistroMedicacaoCreateSerializer(serializers.ModelSerializer):
    agendamento = serializers.PrimaryKeyRelatedField(queryset=Agendamento.objects.all())

    class Meta:
        model = RegistroMedicacao
        fields = ['agendamento', 'tomou', 'data_hora_tomada']
        
class RegistroMedicacaoUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroMedicacao
        
        fields = ['tomou', 'data_hora_tomada']
        extra_kwargs = {
            'tomou': {'required': False},
            'data_hora_tomada': {'required': False},
        }
        
class MedicamentoComAgendamentoSerializer(serializers.Serializer):
    
    nome = serializers.CharField(max_length=255)
    dosagem_valor = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    dosagem_unidade = serializers.CharField(max_length=20, required=False)
    observacao = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    estoque_atual = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    aviso_estoque_minimo = serializers.IntegerField(required=False, allow_null=True)

    horario_inicio = serializers.TimeField()
    horario_fim = serializers.TimeField(required=False, allow_null=True)
    intervalo = serializers.IntegerField(min_value=1, max_value=24)
    duracao_valor = serializers.IntegerField(min_value=1, required=False, allow_null=True)
