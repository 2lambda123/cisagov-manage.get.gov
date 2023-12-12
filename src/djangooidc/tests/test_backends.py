from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from registrar.models import User
from ..backends import OpenIdConnectBackend  # Adjust the import path based on your project structure

class OpenIdConnectBackendTestCase(TestCase):

    def setUp(self):
        self.backend = OpenIdConnectBackend()
        self.kwargs = {
            "sub": "test_user",
            "given_name": "John",
            "family_name": "Doe",
            "email": "john.doe@example.com",
            "phone": "123456789",
        }

    def tearDown(self) -> None:
        User.objects.all().delete()

    def test_authenticate_with_create_user(self):
        """Test that authenticate creates a new user if it does not find
        existing user"""
        # Ensure that the authenticate method creates a new user
        user = self.backend.authenticate(request=None, **self.kwargs)
        self.assertIsNotNone(user)
        self.assertIsInstance(user, User)
        self.assertEqual(user.username, "test_user")

        # Verify that user fields are correctly set
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertEqual(user.phone, "123456789")

    def test_authenticate_with_existing_user(self):
        """Test that authenticate updates an existing user if it finds one.
        For this test, given_name and family_name are supplied"""
        # Create an existing user with the same username
        existing_user = User.objects.create_user(username="test_user")

        # Ensure that the authenticate method updates the existing user
        user = self.backend.authenticate(request=None, **self.kwargs)
        self.assertIsNotNone(user)
        self.assertIsInstance(user, User)
        self.assertEqual(user, existing_user)  # The same user instance should be returned

        # Verify that user fields are correctly updated
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertEqual(user.phone, "123456789")

    def test_authenticate_with_existing_user_no_name(self):
        """Test that authenticate updates an existing user if it finds one.
        For this test, given_name and family_name are supplied"""
        # Create an existing user with the same username and with first and last names
        existing_user = User.objects.create_user(username="test_user",first_name="John",last_name="Doe")

        # Remove given_name and family_name from the input, self.kwargs
        self.kwargs.pop("given_name", None) 
        self.kwargs.pop("family_name", None)

        # Ensure that the authenticate method updates the existing user
        # and preserves existing first and last names
        user = self.backend.authenticate(request=None, **self.kwargs)
        self.assertIsNotNone(user)
        self.assertIsInstance(user, User)
        self.assertEqual(user, existing_user)  # The same user instance should be returned

        # Verify that user fields are correctly updated
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.email, "john.doe@example.com")
        self.assertEqual(user.phone, "123456789")

    def test_authenticate_with_unknown_user(self):
        """Test that authenticate returns None when no kwargs are supplied"""
        # Ensure that the authenticate method handles the case when the user is not found
        user = self.backend.authenticate(request=None, **{})
        self.assertIsNone(user)
