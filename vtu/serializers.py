from rest_framework import serializers
from .models import DataPlan

class DataPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataPlan
        fields = '__all__'
