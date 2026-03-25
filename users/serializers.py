from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number', 'email', 'password', 'username']
        extra_kwargs = {
            'password': {'write_only': True},
            'phone_number': {'required': False, 'allow_blank': True}
        }

    def create(self, validated_data):
        # Hash the password before saving to the database
        validated_data['password'] = make_password(validated_data['password'])
        return super(RegisterSerializer, self).create(validated_data)

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        # Add user data to the response
        data['user'] = {
            'username': self.user.username,
            'email': self.user.email,
            'phone_number': self.user.phone_number,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
        }
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims (optional)
        token['phone_number'] = user.phone_number
        return token