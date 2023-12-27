from django.test import TestCase, RequestFactory, Client
from django.contrib.admin.sites import AdminSite
from contextlib import ExitStack
from django.contrib import messages
from django.urls import reverse

from registrar.admin import (
    DomainAdmin,
    DomainApplicationAdmin,
    DomainApplicationAdminForm,
    DomainInvitationAdmin,
    ListHeaderAdmin,
    MyUserAdmin,
    AuditedAdmin,
    ContactAdmin,
    UserDomainRoleAdmin,
)
from registrar.models import Domain, DomainApplication, DomainInformation, User, DomainInvitation, Contact, Website
from registrar.models.user_domain_role import UserDomainRole
from .common import (
    completed_application,
    generic_domain_object,
    mock_user,
    create_superuser,
    create_user,
    create_ready_domain,
    multiple_unalphabetical_domain_objects,
    MockEppLib,
)
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import get_user_model
from unittest.mock import patch
from unittest import skip

from django.conf import settings
from unittest.mock import MagicMock
import boto3_mocking  # type: ignore
import logging

logger = logging.getLogger(__name__)


class TestDomainAdmin(MockEppLib):
    def setUp(self):
        self.site = AdminSite()
        self.admin = DomainAdmin(model=Domain, admin_site=self.site)
        self.client = Client(HTTP_HOST="localhost:8080")
        self.superuser = create_superuser()
        self.staffuser = create_user()
        self.factory = RequestFactory()
        super().setUp()

    def test_short_org_name_in_domains_list(self):
        """
        Make sure the short name is displaying in admin on the list page
        """
        self.client.force_login(self.superuser)
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)
        application.approve()

        response = self.client.get("/admin/registrar/domain/")

        # There are 3 template references to Federal (3) plus one reference in the table
        # for our actual application
        self.assertContains(response, "Federal", count=4)
        # This may be a bit more robust
        self.assertContains(response, '<td class="field-organization_type">Federal</td>', count=1)
        # Now let's make sure the long description does not exist
        self.assertNotContains(response, "Federal: an agency of the U.S. government")

    @skip("Why did this test stop working, and is is a good test")
    def test_place_and_remove_hold(self):
        domain = create_ready_domain()
        # get admin page and assert Place Hold button
        p = "userpass"
        self.client.login(username="staffuser", password=p)
        response = self.client.get(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Place hold")
        self.assertNotContains(response, "Remove hold")

        # submit place_client_hold and assert Remove Hold button
        response = self.client.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_place_client_hold": "Place hold", "name": domain.name},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Remove hold")
        self.assertNotContains(response, "Place hold")

        # submit remove client hold and assert Place hold button
        response = self.client.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_remove_client_hold": "Remove hold", "name": domain.name},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Place hold")
        self.assertNotContains(response, "Remove hold")

    def test_deletion_is_successful(self):
        """
        Scenario: Domain deletion is unsuccessful
            When the domain is deleted
            Then a user-friendly success message is returned for displaying on the web
            And `state` is et to `DELETED`
        """
        domain = create_ready_domain()
        # Put in client hold
        domain.place_client_hold()
        p = "userpass"
        self.client.login(username="staffuser", password=p)

        # Ensure everything is displaying correctly
        response = self.client.get(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Remove from registry")

        # Test the info dialog
        request = self.factory.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_delete_domain": "Remove from registry", "name": domain.name},
            follow=True,
        )
        request.user = self.client

        with patch("django.contrib.messages.add_message") as mock_add_message:
            self.admin.do_delete_domain(request, domain)
            mock_add_message.assert_called_once_with(
                request,
                messages.INFO,
                "Domain city.gov has been deleted. Thanks!",
                extra_tags="",
                fail_silently=False,
            )

        self.assertEqual(domain.state, Domain.State.DELETED)

    def test_deletion_ready_fsm_failure(self):
        """
        Scenario: Domain deletion is unsuccessful
            When an error is returned from epplibwrapper
            Then a user-friendly error message is returned for displaying on the web
            And `state` is not set to `DELETED`
        """
        domain = create_ready_domain()
        p = "userpass"
        self.client.login(username="staffuser", password=p)

        # Ensure everything is displaying correctly
        response = self.client.get(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Remove from registry")

        # Test the error
        request = self.factory.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_delete_domain": "Remove from registry", "name": domain.name},
            follow=True,
        )
        request.user = self.client

        with patch("django.contrib.messages.add_message") as mock_add_message:
            self.admin.do_delete_domain(request, domain)
            mock_add_message.assert_called_once_with(
                request,
                messages.ERROR,
                "Error deleting this Domain: "
                "Can't switch from state 'ready' to 'deleted'"
                ", must be either 'dns_needed' or 'on_hold'",
                extra_tags="",
                fail_silently=False,
            )

        self.assertEqual(domain.state, Domain.State.READY)

    def test_analyst_deletes_domain_idempotent(self):
        """
        Scenario: Analyst tries to delete an already deleted domain
            Given `state` is already `DELETED`
            When `domain.deletedInEpp()` is called
            Then `commands.DeleteDomain` is sent to the registry
            And Domain returns normally without an error dialog
        """
        domain = create_ready_domain()
        # Put in client hold
        domain.place_client_hold()
        p = "userpass"
        self.client.login(username="staffuser", password=p)

        # Ensure everything is displaying correctly
        response = self.client.get(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, domain.name)
        self.assertContains(response, "Remove from registry")

        # Test the info dialog
        request = self.factory.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_delete_domain": "Remove from registry", "name": domain.name},
            follow=True,
        )
        request.user = self.client

        # Delete it once
        with patch("django.contrib.messages.add_message") as mock_add_message:
            self.admin.do_delete_domain(request, domain)
            mock_add_message.assert_called_once_with(
                request,
                messages.INFO,
                "Domain city.gov has been deleted. Thanks!",
                extra_tags="",
                fail_silently=False,
            )

        self.assertEqual(domain.state, Domain.State.DELETED)

        # Try to delete it again
        # Test the info dialog
        request = self.factory.post(
            "/admin/registrar/domain/{}/change/".format(domain.pk),
            {"_delete_domain": "Remove from registry", "name": domain.name},
            follow=True,
        )
        request.user = self.client

        with patch("django.contrib.messages.add_message") as mock_add_message:
            self.admin.do_delete_domain(request, domain)
            mock_add_message.assert_called_once_with(
                request,
                messages.INFO,
                "This domain is already deleted",
                extra_tags="",
                fail_silently=False,
            )

        self.assertEqual(domain.state, Domain.State.DELETED)

    @skip("Waiting on epp lib to implement")
    def test_place_and_remove_hold_epp(self):
        raise

    def tearDown(self):
        super().tearDown()
        Domain.objects.all().delete()
        DomainInformation.objects.all().delete()
        DomainApplication.objects.all().delete()
        User.objects.all().delete()


class TestDomainApplicationAdminForm(TestCase):
    def setUp(self):
        # Create a test application with an initial state of started
        self.application = completed_application()

    def test_form_choices(self):
        # Create a form instance with the test application
        form = DomainApplicationAdminForm(instance=self.application)

        # Verify that the form choices match the available transitions for started
        expected_choices = [("started", "Started"), ("submitted", "Submitted")]
        self.assertEqual(form.fields["status"].widget.choices, expected_choices)

    def test_form_choices_when_no_instance(self):
        # Create a form instance without an instance
        form = DomainApplicationAdminForm()

        # Verify that the form choices show all choices when no instance is provided;
        # this is necessary to show all choices when creating a new domain
        # application in django admin;
        # note that FSM ensures that no domain application exists with invalid status,
        # so don't need to test for invalid status
        self.assertEqual(
            form.fields["status"].widget.choices,
            DomainApplication._meta.get_field("status").choices,
        )

    def test_form_choices_when_ineligible(self):
        # Create a form instance with a domain application with ineligible status
        ineligible_application = DomainApplication(status="ineligible")

        # Attempt to create a form with the ineligible application
        # The form should not raise an error, but choices should be the
        # full list of possible choices
        form = DomainApplicationAdminForm(instance=ineligible_application)

        self.assertEqual(
            form.fields["status"].widget.choices,
            DomainApplication._meta.get_field("status").choices,
        )


class TestDomainApplicationAdmin(MockEppLib):
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = DomainApplicationAdmin(model=DomainApplication, admin_site=self.site)
        self.superuser = create_superuser()
        self.staffuser = create_user()
        self.client = Client(HTTP_HOST="localhost:8080")

    def test_short_org_name_in_applications_list(self):
        """
        Make sure the short name is displaying in admin on the list page
        """
        self.client.force_login(self.superuser)
        completed_application()
        response = self.client.get("/admin/registrar/domainapplication/")
        # There are 3 template references to Federal (3) plus one reference in the table
        # for our actual application
        self.assertContains(response, "Federal", count=4)
        # This may be a bit more robust
        self.assertContains(response, '<td class="field-organization_type">Federal</td>', count=1)
        # Now let's make sure the long description does not exist
        self.assertNotContains(response, "Federal: an agency of the U.S. government")

    @boto3_mocking.patching
    def test_save_model_sends_submitted_email(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        mock_client = MagicMock()
        mock_client_instance = mock_client.return_value

        with boto3_mocking.clients.handler_for("sesv2", mock_client):
            # Create a sample application
            application = completed_application()

            # Create a mock request
            request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

            # Modify the application's property
            application.status = DomainApplication.ApplicationStatus.SUBMITTED

            # Use the model admin's save_model method
            self.admin.save_model(request, application, form=None, change=True)

        # Access the arguments passed to send_email
        call_args = mock_client_instance.send_email.call_args
        args, kwargs = call_args

        # Retrieve the email details from the arguments
        from_email = kwargs.get("FromEmailAddress")
        to_email = kwargs["Destination"]["ToAddresses"][0]
        email_content = kwargs["Content"]
        email_body = email_content["Simple"]["Body"]["Text"]["Data"]

        # Assert or perform other checks on the email details
        expected_string = "We received your .gov domain request."
        self.assertEqual(from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(to_email, EMAIL)
        self.assertIn(expected_string, email_body)

        # Perform assertions on the mock call itself
        mock_client_instance.send_email.assert_called_once()

    @boto3_mocking.patching
    def test_save_model_sends_in_review_email(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        mock_client = MagicMock()
        mock_client_instance = mock_client.return_value

        with boto3_mocking.clients.handler_for("sesv2", mock_client):
            # Create a sample application
            application = completed_application(status=DomainApplication.ApplicationStatus.SUBMITTED)

            # Create a mock request
            request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

            # Modify the application's property
            application.status = DomainApplication.ApplicationStatus.IN_REVIEW

            # Use the model admin's save_model method
            self.admin.save_model(request, application, form=None, change=True)

        # Access the arguments passed to send_email
        call_args = mock_client_instance.send_email.call_args
        args, kwargs = call_args

        # Retrieve the email details from the arguments
        from_email = kwargs.get("FromEmailAddress")
        to_email = kwargs["Destination"]["ToAddresses"][0]
        email_content = kwargs["Content"]
        email_body = email_content["Simple"]["Body"]["Text"]["Data"]

        # Assert or perform other checks on the email details
        expected_string = "Your .gov domain request is being reviewed."
        self.assertEqual(from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(to_email, EMAIL)
        self.assertIn(expected_string, email_body)

        # Perform assertions on the mock call itself
        mock_client_instance.send_email.assert_called_once()

    @boto3_mocking.patching
    def test_save_model_sends_approved_email(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        mock_client = MagicMock()
        mock_client_instance = mock_client.return_value

        with boto3_mocking.clients.handler_for("sesv2", mock_client):
            # Create a sample application
            application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)

            # Create a mock request
            request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

            # Modify the application's property
            application.status = DomainApplication.ApplicationStatus.APPROVED

            # Use the model admin's save_model method
            self.admin.save_model(request, application, form=None, change=True)

        # Access the arguments passed to send_email
        call_args = mock_client_instance.send_email.call_args
        args, kwargs = call_args

        # Retrieve the email details from the arguments
        from_email = kwargs.get("FromEmailAddress")
        to_email = kwargs["Destination"]["ToAddresses"][0]
        email_content = kwargs["Content"]
        email_body = email_content["Simple"]["Body"]["Text"]["Data"]

        # Assert or perform other checks on the email details
        expected_string = "Congratulations! Your .gov domain request has been approved."
        self.assertEqual(from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(to_email, EMAIL)
        self.assertIn(expected_string, email_body)

        # Perform assertions on the mock call itself
        mock_client_instance.send_email.assert_called_once()

    def test_save_model_sets_approved_domain(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        # Create a sample application
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)

        # Create a mock request
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

        # Modify the application's property
        application.status = DomainApplication.ApplicationStatus.APPROVED

        # Use the model admin's save_model method
        self.admin.save_model(request, application, form=None, change=True)

        # Test that approved domain exists and equals requested domain
        self.assertEqual(application.requested_domain.name, application.approved_domain.name)

    @boto3_mocking.patching
    def test_save_model_sends_action_needed_email(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        mock_client = MagicMock()
        mock_client_instance = mock_client.return_value

        with boto3_mocking.clients.handler_for("sesv2", mock_client):
            # Create a sample application
            application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)

            # Create a mock request
            request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

            # Modify the application's property
            application.status = DomainApplication.ApplicationStatus.ACTION_NEEDED

            # Use the model admin's save_model method
            self.admin.save_model(request, application, form=None, change=True)

        # Access the arguments passed to send_email
        call_args = mock_client_instance.send_email.call_args
        args, kwargs = call_args

        # Retrieve the email details from the arguments
        from_email = kwargs.get("FromEmailAddress")
        to_email = kwargs["Destination"]["ToAddresses"][0]
        email_content = kwargs["Content"]
        email_body = email_content["Simple"]["Body"]["Text"]["Data"]

        # Assert or perform other checks on the email details
        expected_string = "We've identified an action needed to complete the review of your .gov domain request."
        self.assertEqual(from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(to_email, EMAIL)
        self.assertIn(expected_string, email_body)

        # Perform assertions on the mock call itself
        mock_client_instance.send_email.assert_called_once()

    @boto3_mocking.patching
    def test_save_model_sends_rejected_email(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        mock_client = MagicMock()
        mock_client_instance = mock_client.return_value

        with boto3_mocking.clients.handler_for("sesv2", mock_client):
            # Create a sample application
            application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)

            # Create a mock request
            request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

            # Modify the application's property
            application.status = DomainApplication.ApplicationStatus.REJECTED

            # Use the model admin's save_model method
            self.admin.save_model(request, application, form=None, change=True)

        # Access the arguments passed to send_email
        call_args = mock_client_instance.send_email.call_args
        args, kwargs = call_args

        # Retrieve the email details from the arguments
        from_email = kwargs.get("FromEmailAddress")
        to_email = kwargs["Destination"]["ToAddresses"][0]
        email_content = kwargs["Content"]
        email_body = email_content["Simple"]["Body"]["Text"]["Data"]

        # Assert or perform other checks on the email details
        expected_string = "Your .gov domain request has been rejected."
        self.assertEqual(from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(to_email, EMAIL)
        self.assertIn(expected_string, email_body)

        # Perform assertions on the mock call itself
        mock_client_instance.send_email.assert_called_once()

    def test_save_model_sets_restricted_status_on_user(self):
        # make sure there is no user with this email
        EMAIL = "mayor@igorville.gov"
        User.objects.filter(email=EMAIL).delete()

        # Create a sample application
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)

        # Create a mock request
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

        # Modify the application's property
        application.status = DomainApplication.ApplicationStatus.INELIGIBLE

        # Use the model admin's save_model method
        self.admin.save_model(request, application, form=None, change=True)

        # Test that approved domain exists and equals requested domain
        self.assertEqual(application.creator.status, "restricted")

    def test_readonly_when_restricted_creator(self):
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)
        application.creator.status = User.RESTRICTED
        application.creator.save()

        request = self.factory.get("/")
        request.user = self.superuser

        readonly_fields = self.admin.get_readonly_fields(request, application)

        expected_fields = [
            "id",
            "created_at",
            "updated_at",
            "status",
            "creator",
            "investigator",
            "organization_type",
            "federally_recognized_tribe",
            "state_recognized_tribe",
            "tribe_name",
            "federal_agency",
            "federal_type",
            "is_election_board",
            "organization_name",
            "address_line1",
            "address_line2",
            "city",
            "state_territory",
            "zipcode",
            "urbanization",
            "about_your_organization",
            "authorizing_official",
            "approved_domain",
            "requested_domain",
            "submitter",
            "purpose",
            "no_other_contacts_rationale",
            "anything_else",
            "is_policy_acknowledged",
            "submission_date",
            "current_websites",
            "other_contacts",
            "alternative_domains",
        ]

        self.assertEqual(readonly_fields, expected_fields)

    def test_readonly_fields_for_analyst(self):
        request = self.factory.get("/")  # Use the correct method and path
        request.user = self.staffuser

        readonly_fields = self.admin.get_readonly_fields(request)

        expected_fields = [
            "creator",
            "about_your_organization",
            "requested_domain",
            "alternative_domains",
            "purpose",
            "submitter",
            "no_other_contacts_rationale",
            "anything_else",
            "is_policy_acknowledged",
        ]

        self.assertEqual(readonly_fields, expected_fields)

    def test_readonly_fields_for_superuser(self):
        request = self.factory.get("/")  # Use the correct method and path
        request.user = self.superuser

        readonly_fields = self.admin.get_readonly_fields(request)

        expected_fields = []

        self.assertEqual(readonly_fields, expected_fields)

    def test_saving_when_restricted_creator(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)
        application.creator.status = User.RESTRICTED
        application.creator.save()

        # Create a request object with a superuser
        request = self.factory.get("/")
        request.user = self.superuser

        with patch("django.contrib.messages.error") as mock_error:
            # Simulate saving the model
            self.admin.save_model(request, application, None, False)

            # Assert that the error message was called with the correct argument
            mock_error.assert_called_once_with(
                request,
                "This action is not permitted for applications with a restricted creator.",
            )

        # Assert that the status has not changed
        self.assertEqual(application.status, DomainApplication.ApplicationStatus.IN_REVIEW)

    def test_change_view_with_restricted_creator(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.IN_REVIEW)
        application.creator.status = User.RESTRICTED
        application.creator.save()

        with patch("django.contrib.messages.warning") as mock_warning:
            # Create a request object with a superuser
            request = self.factory.get("/admin/your_app/domainapplication/{}/change/".format(application.pk))
            request.user = self.superuser

            self.admin.display_restricted_warning(request, application)

            # Assert that the error message was called with the correct argument
            mock_warning.assert_called_once_with(
                request,
                "Cannot edit an application with a restricted creator.",
            )

    def test_error_when_saving_approved_to_rejected_and_domain_is_active(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.APPROVED)
        domain = Domain.objects.create(name=application.requested_domain.name)
        application.approved_domain = domain
        application.save()

        # Create a request object with a superuser
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))
        request.user = self.superuser

        # Define a custom implementation for is_active
        def custom_is_active(self):
            return True  # Override to return True

        # Use ExitStack to combine patch contexts
        with ExitStack() as stack:
            # Patch Domain.is_active and django.contrib.messages.error simultaneously
            stack.enter_context(patch.object(Domain, "is_active", custom_is_active))
            stack.enter_context(patch.object(messages, "error"))

            # Simulate saving the model
            application.status = DomainApplication.ApplicationStatus.REJECTED
            self.admin.save_model(request, application, None, True)

            # Assert that the error message was called with the correct argument
            messages.error.assert_called_once_with(
                request,
                "This action is not permitted. The domain " + "is already active.",
            )

    def test_side_effects_when_saving_approved_to_rejected(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.APPROVED)
        domain = Domain.objects.create(name=application.requested_domain.name)
        domain_information = DomainInformation.objects.create(creator=self.superuser, domain=domain)
        application.approved_domain = domain
        application.save()

        # Create a request object with a superuser
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))
        request.user = self.superuser

        # Define a custom implementation for is_active
        def custom_is_active(self):
            return False  # Override to return False

        # Use ExitStack to combine patch contexts
        with ExitStack() as stack:
            # Patch Domain.is_active and django.contrib.messages.error simultaneously
            stack.enter_context(patch.object(Domain, "is_active", custom_is_active))
            stack.enter_context(patch.object(messages, "error"))

            # Simulate saving the model
            application.status = DomainApplication.ApplicationStatus.REJECTED
            self.admin.save_model(request, application, None, True)

            # Assert that the error message was never called
            messages.error.assert_not_called()

        self.assertEqual(application.approved_domain, None)

        # Assert that Domain got Deleted
        with self.assertRaises(Domain.DoesNotExist):
            domain.refresh_from_db()

        # Assert that DomainInformation got Deleted
        with self.assertRaises(DomainInformation.DoesNotExist):
            domain_information.refresh_from_db()

    def test_error_when_saving_approved_to_ineligible_and_domain_is_active(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.APPROVED)
        domain = Domain.objects.create(name=application.requested_domain.name)
        application.approved_domain = domain
        application.save()

        # Create a request object with a superuser
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))
        request.user = self.superuser

        # Define a custom implementation for is_active
        def custom_is_active(self):
            return True  # Override to return True

        # Use ExitStack to combine patch contexts
        with ExitStack() as stack:
            # Patch Domain.is_active and django.contrib.messages.error simultaneously
            stack.enter_context(patch.object(Domain, "is_active", custom_is_active))
            stack.enter_context(patch.object(messages, "error"))

            # Simulate saving the model
            application.status = DomainApplication.ApplicationStatus.INELIGIBLE
            self.admin.save_model(request, application, None, True)

            # Assert that the error message was called with the correct argument
            messages.error.assert_called_once_with(
                request,
                "This action is not permitted. The domain " + "is already active.",
            )

    def test_side_effects_when_saving_approved_to_ineligible(self):
        # Create an instance of the model
        application = completed_application(status=DomainApplication.ApplicationStatus.APPROVED)
        domain = Domain.objects.create(name=application.requested_domain.name)
        domain_information = DomainInformation.objects.create(creator=self.superuser, domain=domain)
        application.approved_domain = domain
        application.save()

        # Create a request object with a superuser
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))
        request.user = self.superuser

        # Define a custom implementation for is_active
        def custom_is_active(self):
            return False  # Override to return False

        # Use ExitStack to combine patch contexts
        with ExitStack() as stack:
            # Patch Domain.is_active and django.contrib.messages.error simultaneously
            stack.enter_context(patch.object(Domain, "is_active", custom_is_active))
            stack.enter_context(patch.object(messages, "error"))

            # Simulate saving the model
            application.status = DomainApplication.ApplicationStatus.INELIGIBLE
            self.admin.save_model(request, application, None, True)

            # Assert that the error message was never called
            messages.error.assert_not_called()

        self.assertEqual(application.approved_domain, None)

        # Assert that Domain got Deleted
        with self.assertRaises(Domain.DoesNotExist):
            domain.refresh_from_db()

        # Assert that DomainInformation got Deleted
        with self.assertRaises(DomainInformation.DoesNotExist):
            domain_information.refresh_from_db()

    def test_has_correct_filters(self):
        """
        This test verifies that DomainApplicationAdmin has the correct filters set up.

        It retrieves the current list of filters from DomainApplicationAdmin
        and checks that it matches the expected list of filters.
        """
        request = self.factory.get("/")
        request.user = self.superuser

        # Grab the current list of table filters
        readonly_fields = self.admin.get_list_filter(request)
        expected_fields = ("status", "organization_type", DomainApplicationAdmin.InvestigatorFilter)

        self.assertEqual(readonly_fields, expected_fields)

    def test_table_sorted_alphabetically(self):
        """
        This test verifies that the DomainApplicationAdmin table is sorted alphabetically
        by the 'requested_domain__name' field.

        It creates a list of DomainApplication instances in a non-alphabetical order,
        then retrieves the queryset from the DomainApplicationAdmin and checks
        that it matches the expected queryset,
        which is sorted alphabetically by the 'requested_domain__name' field.
        """
        # Creates a list of DomainApplications in scrambled order
        multiple_unalphabetical_domain_objects("application")

        request = self.factory.get("/")
        request.user = self.superuser

        # Get the expected list of alphabetically sorted DomainApplications
        expected_order = DomainApplication.objects.order_by("requested_domain__name")

        # Get the returned queryset
        queryset = self.admin.get_queryset(request)

        # Check the order
        self.assertEqual(
            list(queryset),
            list(expected_order),
        )

    def test_displays_investigator_filter(self):
        """
        This test verifies that the investigator filter in the admin interface for
        the DomainApplication model displays correctly.

        It creates two DomainApplication instances, each with a different investigator.
        It then simulates a staff user logging in and applying the investigator filter
        on the DomainApplication admin page.

        We then test if the page displays the filter we expect, but we do not test
        if we get back the correct response in the table. This is to isolate if
        the filter displays correctly, when the filter isn't filtering correctly.
        """

        # Create a mock DomainApplication object, with a fake investigator
        application: DomainApplication = generic_domain_object("application", "SomeGuy")
        investigator_user = User.objects.filter(username=application.investigator.username).get()
        investigator_user.is_staff = True
        investigator_user.save()

        p = "userpass"
        self.client.login(username="staffuser", password=p)
        response = self.client.get(
            "/admin/registrar/domainapplication/",
            {
                "investigator__id__exact": investigator_user.id,
            },
            follow=True,
        )

        # Then, test if the filter actually exists
        self.assertIn("filters", response.context)

        # Assert the content of filters and search_query
        filters = response.context["filters"]

        self.assertEqual(
            filters,
            [
                {
                    "parameter_name": "investigator",
                    "parameter_value": "SomeGuy first_name:investigator SomeGuy last_name:investigator",
                },
            ],
        )

    def test_investigator_filter_filters_correctly(self):
        """
        This test verifies that the investigator filter in the admin interface for
        the DomainApplication model works correctly.

        It creates two DomainApplication instances, each with a different investigator.
        It then simulates a staff user logging in and applying the investigator filter
        on the DomainApplication admin page.

        It then verifies that it was applied correctly.
        The test checks that the response contains the expected DomainApplication pbjects
        in the table.
        """

        # Create a mock DomainApplication object, with a fake investigator
        application: DomainApplication = generic_domain_object("application", "SomeGuy")
        investigator_user = User.objects.filter(username=application.investigator.username).get()
        investigator_user.is_staff = True
        investigator_user.save()

        # Create a second mock DomainApplication object, to test filtering
        application: DomainApplication = generic_domain_object("application", "BadGuy")
        another_user = User.objects.filter(username=application.investigator.username).get()
        another_user.is_staff = True
        another_user.save()

        p = "userpass"
        self.client.login(username="staffuser", password=p)
        response = self.client.get(
            "/admin/registrar/domainapplication/",
            {
                "investigator__id__exact": investigator_user.id,
            },
            follow=True,
        )

        expected_name = "SomeGuy first_name:investigator SomeGuy last_name:investigator"
        # We expect to see this four times, two of them are from the html for the filter,
        # and the other two are the html from the list entry in the table.
        self.assertContains(response, expected_name, count=4)

        # Check that we don't also get the thing we aren't filtering for.
        # We expect to see this two times in the filter
        unexpected_name = "BadGuy first_name:investigator BadGuy last_name:investigator"
        self.assertContains(response, unexpected_name, count=2)

    def test_investigator_dropdown_displays_only_staff(self):
        """
        This test verifies that the dropdown for the 'investigator' field in the DomainApplicationAdmin
        interface only displays users who are marked as staff.

        It creates two DomainApplication instances, one with an investigator
        who is a staff user and another with an investigator who is not a staff user.

        It then retrieves the queryset for the 'investigator' dropdown from DomainApplicationAdmin
        and checks that it matches the expected queryset, which only includes staff users.
        """
        # Create a mock DomainApplication object, with a fake investigator
        application: DomainApplication = generic_domain_object("application", "SomeGuy")
        investigator_user = User.objects.filter(username=application.investigator.username).get()
        investigator_user.is_staff = True
        investigator_user.save()

        # Create a mock DomainApplication object, with a user that is not staff
        application_2: DomainApplication = generic_domain_object("application", "SomeOtherGuy")
        investigator_user_2 = User.objects.filter(username=application_2.investigator.username).get()
        investigator_user_2.is_staff = False
        investigator_user_2.save()

        p = "userpass"
        self.client.login(username="staffuser", password=p)

        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(application.pk))

        # Get the actual field from the model's meta information
        investigator_field = DomainApplication._meta.get_field("investigator")

        # We should only be displaying staff users, in alphabetical order
        expected_dropdown = list(User.objects.filter(is_staff=True))
        current_dropdown = list(self.admin.formfield_for_foreignkey(investigator_field, request).queryset)

        self.assertEqual(expected_dropdown, current_dropdown)

        # Non staff users should not be in the list
        self.assertNotIn(application_2, current_dropdown)

    def test_investigator_list_is_alphabetically_sorted(self):
        """
        This test verifies that filter list for the 'investigator'
        is displayed alphabetically
        """
        # Create a mock DomainApplication object, with a fake investigator
        application: DomainApplication = generic_domain_object("application", "SomeGuy")
        investigator_user = User.objects.filter(username=application.investigator.username).get()
        investigator_user.is_staff = True
        investigator_user.save()

        application_2: DomainApplication = generic_domain_object("application", "AGuy")
        investigator_user_2 = User.objects.filter(username=application_2.investigator.username).get()
        investigator_user_2.first_name = "AGuy"
        investigator_user_2.is_staff = True
        investigator_user_2.save()

        application_3: DomainApplication = generic_domain_object("application", "FinalGuy")
        investigator_user_3 = User.objects.filter(username=application_3.investigator.username).get()
        investigator_user_3.first_name = "FinalGuy"
        investigator_user_3.is_staff = True
        investigator_user_3.save()

        p = "userpass"
        self.client.login(username="staffuser", password=p)
        request = RequestFactory().get("/")

        expected_list = list(User.objects.filter(is_staff=True).order_by("first_name", "last_name", "email"))

        # Get the actual sorted list of investigators from the lookups method
        actual_list = [item for _, item in self.admin.InvestigatorFilter.lookups(self, request, self.admin)]

        self.assertEqual(expected_list, actual_list)

    def tearDown(self):
        super().tearDown()
        Domain.objects.all().delete()
        DomainInformation.objects.all().delete()
        DomainApplication.objects.all().delete()
        User.objects.all().delete()
        Contact.objects.all().delete()
        Website.objects.all().delete()


class DomainInvitationAdminTest(TestCase):
    """Tests for the DomainInvitation page"""

    def setUp(self):
        """Create a client object"""
        self.client = Client(HTTP_HOST="localhost:8080")
        self.factory = RequestFactory()
        self.admin = ListHeaderAdmin(model=DomainInvitationAdmin, admin_site=AdminSite())
        self.superuser = create_superuser()

    def tearDown(self):
        """Delete all DomainInvitation objects"""
        DomainInvitation.objects.all().delete()

    def test_get_filters(self):
        """Ensures that our filters are displaying correctly"""
        # Have to get creative to get past linter
        p = "adminpass"
        self.client.login(username="superuser", password=p)

        response = self.client.get(
            "/admin/registrar/domaininvitation/",
            {},
            follow=True,
        )

        # Assert that the filters are added
        self.assertContains(response, "invited", count=2)
        self.assertContains(response, "Invited", count=2)
        self.assertContains(response, "retrieved", count=2)
        self.assertContains(response, "Retrieved", count=2)

        # Check for the HTML context specificially
        invited_html = '<a href="?status__exact=invited">Invited</a>'
        retrieved_html = '<a href="?status__exact=retrieved">Retrieved</a>'

        self.assertContains(response, invited_html, count=1)
        self.assertContains(response, retrieved_html, count=1)


class UserDomainRoleAdminTest(TestCase):
    def setUp(self):
        """Setup environment for a mock admin user"""
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = ListHeaderAdmin(model=UserDomainRoleAdmin, admin_site=None)
        self.client = Client(HTTP_HOST="localhost:8080")
        self.superuser = create_superuser()

    def tearDown(self):
        """Delete all Users, Domains, and UserDomainRoles"""
        User.objects.all().delete()
        Domain.objects.all().delete()
        UserDomainRole.objects.all().delete()

    def test_email_not_in_search(self):
        """Tests the search bar in Django Admin for UserDomainRoleAdmin.
        Should return no results for an invalid email."""
        # Have to get creative to get past linter
        p = "adminpass"
        self.client.login(username="superuser", password=p)

        fake_user = User.objects.create(
            username="dummyuser", first_name="Stewart", last_name="Jones", email="AntarcticPolarBears@example.com"
        )
        fake_domain = Domain.objects.create(name="test123")
        UserDomainRole.objects.create(user=fake_user, domain=fake_domain, role="manager")
        # Make the request using the Client class
        # which handles CSRF
        # Follow=True handles the redirect
        response = self.client.get(
            "/admin/registrar/userdomainrole/",
            {
                "q": "testmail@igorville.com",
            },
            follow=True,
        )

        # Assert that the query is added to the extra_context
        self.assertIn("search_query", response.context)
        # Assert the content of filters and search_query
        search_query = response.context["search_query"]
        self.assertEqual(search_query, "testmail@igorville.com")

        # We only need to check for the end of the HTML string
        self.assertNotContains(response, "Stewart Jones AntarcticPolarBears@example.com</a></th>")

    def test_email_in_search(self):
        """Tests the search bar in Django Admin for UserDomainRoleAdmin.
        Should return results for an valid email."""
        # Have to get creative to get past linter
        p = "adminpass"
        self.client.login(username="superuser", password=p)

        fake_user = User.objects.create(
            username="dummyuser", first_name="Joe", last_name="Jones", email="AntarcticPolarBears@example.com"
        )
        fake_domain = Domain.objects.create(name="fake")
        UserDomainRole.objects.create(user=fake_user, domain=fake_domain, role="manager")
        # Make the request using the Client class
        # which handles CSRF
        # Follow=True handles the redirect
        response = self.client.get(
            "/admin/registrar/userdomainrole/",
            {
                "q": "AntarcticPolarBears@example.com",
            },
            follow=True,
        )

        # Assert that the query is added to the extra_context
        self.assertIn("search_query", response.context)

        search_query = response.context["search_query"]
        self.assertEqual(search_query, "AntarcticPolarBears@example.com")

        # We only need to check for the end of the HTML string
        self.assertContains(response, "Joe Jones AntarcticPolarBears@example.com</a></th>", count=1)


class ListHeaderAdminTest(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = ListHeaderAdmin(model=DomainApplication, admin_site=None)
        self.client = Client(HTTP_HOST="localhost:8080")
        self.superuser = create_superuser()

    def test_changelist_view(self):
        # Have to get creative to get past linter
        p = "adminpass"
        self.client.login(username="superuser", password=p)

        # Mock a user
        user = mock_user()

        # Make the request using the Client class
        # which handles CSRF
        # Follow=True handles the redirect
        response = self.client.get(
            "/admin/registrar/domainapplication/",
            {
                "status__exact": "started",
                "investigator__id__exact": user.id,
                "q": "Hello",
            },
            follow=True,
        )

        # Assert that the filters and search_query are added to the extra_context
        self.assertIn("filters", response.context)
        self.assertIn("search_query", response.context)
        # Assert the content of filters and search_query
        filters = response.context["filters"]
        search_query = response.context["search_query"]
        self.assertEqual(search_query, "Hello")
        self.assertEqual(
            filters,
            [
                {"parameter_name": "status", "parameter_value": "started"},
                {
                    "parameter_name": "investigator",
                    "parameter_value": user.first_name + " " + user.last_name,
                },
            ],
        )

    def test_get_filters(self):
        # Create a mock request object
        request = self.factory.get("/admin/yourmodel/")
        # Set the GET parameters for testing
        request.GET = {
            "status": "started",
            "investigator": "Jeff Lebowski",
            "q": "search_value",
        }
        # Call the get_filters method
        filters = self.admin.get_filters(request)

        # Assert the filters extracted from the request GET
        self.assertEqual(
            filters,
            [
                {"parameter_name": "status", "parameter_value": "started"},
                {"parameter_name": "investigator", "parameter_value": "Jeff Lebowski"},
            ],
        )

    def tearDown(self):
        # delete any applications too
        DomainInformation.objects.all().delete()
        DomainApplication.objects.all().delete()
        User.objects.all().delete()


class MyUserAdminTest(TestCase):
    def setUp(self):
        admin_site = AdminSite()
        self.admin = MyUserAdmin(model=get_user_model(), admin_site=admin_site)

    def test_list_display_without_username(self):
        request = self.client.request().wsgi_request
        request.user = create_user()

        list_display = self.admin.get_list_display(request)
        expected_list_display = [
            "email",
            "first_name",
            "last_name",
            "group",
            "status",
        ]

        self.assertEqual(list_display, expected_list_display)
        self.assertNotIn("username", list_display)

    def test_get_fieldsets_superuser(self):
        request = self.client.request().wsgi_request
        request.user = create_superuser()
        fieldsets = self.admin.get_fieldsets(request)
        expected_fieldsets = super(MyUserAdmin, self.admin).get_fieldsets(request)
        self.assertEqual(fieldsets, expected_fieldsets)

    def test_get_fieldsets_cisa_analyst(self):
        request = self.client.request().wsgi_request
        request.user = create_user()
        fieldsets = self.admin.get_fieldsets(request)
        expected_fieldsets = (
            (None, {"fields": ("password", "status")}),
            ("Personal Info", {"fields": ("first_name", "last_name", "email")}),
            ("Permissions", {"fields": ("is_active", "groups")}),
            ("Important dates", {"fields": ("last_login", "date_joined")}),
        )
        self.assertEqual(fieldsets, expected_fieldsets)

    def tearDown(self):
        User.objects.all().delete()


class AuditedAdminTest(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.client = Client(HTTP_HOST="localhost:8080")

    def order_by_desired_field_helper(self, obj_to_sort: AuditedAdmin, request, field_name, *obj_names):
        formatted_sort_fields = []
        for obj in obj_names:
            formatted_sort_fields.append("{}__{}".format(field_name, obj))

        ordered_list = list(
            obj_to_sort.get_queryset(request).order_by(*formatted_sort_fields).values_list(*formatted_sort_fields)
        )

        return ordered_list

    def test_alphabetically_sorted_fk_fields_domain_application(self):
        tested_fields = [
            DomainApplication.authorizing_official.field,
            DomainApplication.submitter.field,
            DomainApplication.investigator.field,
            DomainApplication.creator.field,
            DomainApplication.requested_domain.field,
        ]

        # Creates multiple domain applications - review status does not matter
        applications = multiple_unalphabetical_domain_objects("application")

        # Create a mock request
        request = self.factory.post("/admin/registrar/domainapplication/{}/change/".format(applications[0].pk))

        model_admin = AuditedAdmin(DomainApplication, self.site)

        sorted_fields = []
        # Typically we wouldn't want two nested for fields,
        # but both fields are of a fixed length.
        # For test case purposes, this should be performant.
        for field in tested_fields:
            isNamefield: bool = field == DomainApplication.requested_domain.field
            if isNamefield:
                sorted_fields = ["name"]
            else:
                sorted_fields = ["first_name", "last_name"]
            # We want both of these to be lists, as it is richer test wise.

            desired_order = self.order_by_desired_field_helper(model_admin, request, field.name, *sorted_fields)
            current_sort_order = list(model_admin.formfield_for_foreignkey(field, request).queryset)

            # Conforms to the same object structure as desired_order
            current_sort_order_coerced_type = []

            # This is necessary as .queryset and get_queryset
            # return lists of different types/structures.
            # We need to parse this data and coerce them into the same type.
            for contact in current_sort_order:
                if not isNamefield:
                    first = contact.first_name
                    last = contact.last_name
                else:
                    first = contact.name
                    last = None

                name_tuple = self.coerced_fk_field_helper(first, last, field.name, ":")
                if name_tuple is not None:
                    current_sort_order_coerced_type.append(name_tuple)

            self.assertEqual(
                desired_order,
                current_sort_order_coerced_type,
                "{} is not ordered alphabetically".format(field.name),
            )

    def test_alphabetically_sorted_fk_fields_domain_information(self):
        tested_fields = [
            DomainInformation.authorizing_official.field,
            DomainInformation.submitter.field,
            # DomainInformation.creator.field,
            (DomainInformation.domain.field, ["name"]),
            (DomainInformation.domain_application.field, ["requested_domain__name"]),
        ]
        # Creates multiple domain applications - review status does not matter
        applications = multiple_unalphabetical_domain_objects("information")

        # Create a mock request
        request = self.factory.post("/admin/registrar/domaininformation/{}/change/".format(applications[0].pk))

        model_admin = AuditedAdmin(DomainInformation, self.site)

        sorted_fields = []
        # Typically we wouldn't want two nested for fields,
        # but both fields are of a fixed length.
        # For test case purposes, this should be performant.
        for field in tested_fields:
            isOtherOrderfield: bool = isinstance(field, tuple)
            field_obj = None
            if isOtherOrderfield:
                sorted_fields = field[1]
                field_obj = field[0]
            else:
                sorted_fields = ["first_name", "last_name"]
                field_obj = field
            # We want both of these to be lists, as it is richer test wise.
            desired_order = self.order_by_desired_field_helper(model_admin, request, field_obj.name, *sorted_fields)
            current_sort_order = list(model_admin.formfield_for_foreignkey(field_obj, request).queryset)

            # Conforms to the same object structure as desired_order
            current_sort_order_coerced_type = []

            # This is necessary as .queryset and get_queryset
            # return lists of different types/structures.
            # We need to parse this data and coerce them into the same type.
            for obj in current_sort_order:
                last = None
                if not isOtherOrderfield:
                    first = obj.first_name
                    last = obj.last_name
                elif field_obj == DomainInformation.domain.field:
                    first = obj.name
                elif field_obj == DomainInformation.domain_application.field:
                    first = obj.requested_domain.name

                name_tuple = self.coerced_fk_field_helper(first, last, field_obj.name, ":")
                if name_tuple is not None:
                    current_sort_order_coerced_type.append(name_tuple)

            self.assertEqual(
                desired_order,
                current_sort_order_coerced_type,
                "{} is not ordered alphabetically".format(field_obj.name),
            )

    def test_alphabetically_sorted_fk_fields_domain_invitation(self):
        tested_fields = [DomainInvitation.domain.field]

        # Creates multiple domain applications - review status does not matter
        applications = multiple_unalphabetical_domain_objects("invitation")

        # Create a mock request
        request = self.factory.post("/admin/registrar/domaininvitation/{}/change/".format(applications[0].pk))

        model_admin = AuditedAdmin(DomainInvitation, self.site)

        sorted_fields = []
        # Typically we wouldn't want two nested for fields,
        # but both fields are of a fixed length.
        # For test case purposes, this should be performant.
        for field in tested_fields:
            sorted_fields = ["name"]
            # We want both of these to be lists, as it is richer test wise.

            desired_order = self.order_by_desired_field_helper(model_admin, request, field.name, *sorted_fields)
            current_sort_order = list(model_admin.formfield_for_foreignkey(field, request).queryset)

            # Conforms to the same object structure as desired_order
            current_sort_order_coerced_type = []

            # This is necessary as .queryset and get_queryset
            # return lists of different types/structures.
            # We need to parse this data and coerce them into the same type.
            for contact in current_sort_order:
                first = contact.name
                last = None

                name_tuple = self.coerced_fk_field_helper(first, last, field.name, ":")
                if name_tuple is not None:
                    current_sort_order_coerced_type.append(name_tuple)

            self.assertEqual(
                desired_order,
                current_sort_order_coerced_type,
                "{} is not ordered alphabetically".format(field.name),
            )

    def coerced_fk_field_helper(self, first_name, last_name, field_name, queryset_shorthand):
        """Handles edge cases for test cases"""
        if first_name is None:
            raise ValueError("Invalid value for first_name, must be defined")

        returned_tuple = (first_name, last_name)
        # Handles edge case for names - structured strangely
        if last_name is None:
            return (first_name,)

        if first_name.split(queryset_shorthand)[1] == field_name:
            return returned_tuple
        else:
            return None

    def tearDown(self):
        DomainInformation.objects.all().delete()
        DomainApplication.objects.all().delete()
        DomainInvitation.objects.all().delete()


class DomainSessionVariableTest(TestCase):
    """Test cases for session variables in Django Admin"""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = DomainAdmin(Domain, None)
        self.client = Client(HTTP_HOST="localhost:8080")

    def test_session_vars_set_correctly(self):
        """Checks if session variables are being set correctly"""

        p = "adminpass"
        self.client.login(username="superuser", password=p)

        dummy_domain_information = generic_domain_object("information", "session")
        request = self.get_factory_post_edit_domain(dummy_domain_information.domain.pk)
        self.populate_session_values(request, dummy_domain_information.domain)
        self.assertEqual(request.session["analyst_action"], "edit")
        self.assertEqual(
            request.session["analyst_action_location"],
            dummy_domain_information.domain.pk,
        )

    def test_session_vars_set_correctly_hardcoded_domain(self):
        """Checks if session variables are being set correctly"""

        p = "adminpass"
        self.client.login(username="superuser", password=p)

        dummy_domain_information: Domain = generic_domain_object("information", "session")
        dummy_domain_information.domain.pk = 1

        request = self.get_factory_post_edit_domain(dummy_domain_information.domain.pk)
        self.populate_session_values(request, dummy_domain_information.domain)
        self.assertEqual(request.session["analyst_action"], "edit")
        self.assertEqual(request.session["analyst_action_location"], 1)

    def test_session_variables_reset_correctly(self):
        """Checks if incorrect session variables get overridden"""

        p = "adminpass"
        self.client.login(username="superuser", password=p)

        dummy_domain_information = generic_domain_object("information", "session")
        request = self.get_factory_post_edit_domain(dummy_domain_information.domain.pk)

        self.populate_session_values(request, dummy_domain_information.domain, preload_bad_data=True)

        self.assertEqual(request.session["analyst_action"], "edit")
        self.assertEqual(
            request.session["analyst_action_location"],
            dummy_domain_information.domain.pk,
        )

    def test_session_variables_retain_information(self):
        """Checks to see if session variables retain old information"""

        p = "adminpass"
        self.client.login(username="superuser", password=p)

        dummy_domain_information_list = multiple_unalphabetical_domain_objects("information")
        for item in dummy_domain_information_list:
            request = self.get_factory_post_edit_domain(item.domain.pk)
            self.populate_session_values(request, item.domain)

            self.assertEqual(request.session["analyst_action"], "edit")
            self.assertEqual(request.session["analyst_action_location"], item.domain.pk)

    def test_session_variables_concurrent_requests(self):
        """Simulates two requests at once"""

        p = "adminpass"
        self.client.login(username="superuser", password=p)

        info_first = generic_domain_object("information", "session")
        info_second = generic_domain_object("information", "session2")

        request_first = self.get_factory_post_edit_domain(info_first.domain.pk)
        request_second = self.get_factory_post_edit_domain(info_second.domain.pk)

        self.populate_session_values(request_first, info_first.domain, True)
        self.populate_session_values(request_second, info_second.domain, True)

        # Check if anything got nulled out
        self.assertNotEqual(request_first.session["analyst_action"], None)
        self.assertNotEqual(request_second.session["analyst_action"], None)
        self.assertNotEqual(request_first.session["analyst_action_location"], None)
        self.assertNotEqual(request_second.session["analyst_action_location"], None)

        # Check if they are both the same action 'type'
        self.assertEqual(request_first.session["analyst_action"], "edit")
        self.assertEqual(request_second.session["analyst_action"], "edit")

        # Check their locations, and ensure they aren't the same across both
        self.assertNotEqual(
            request_first.session["analyst_action_location"],
            request_second.session["analyst_action_location"],
        )

    def populate_session_values(self, request, domain_object, preload_bad_data=False):
        """Boilerplate for creating mock sessions"""
        request.user = self.client
        request.session = SessionStore()
        request.session.create()
        if preload_bad_data:
            request.session["analyst_action"] = "invalid"
            request.session["analyst_action_location"] = "bad location"
        self.admin.response_change(request, domain_object)

    def get_factory_post_edit_domain(self, primary_key):
        """Posts to registrar domain change
        with the edit domain button 'clicked',
        then returns the factory object"""
        return self.factory.post(
            reverse("admin:registrar_domain_change", args=(primary_key,)),
            {"_edit_domain": "true"},
            follow=True,
        )


class ContactAdminTest(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.client = Client(HTTP_HOST="localhost:8080")
        self.admin = ContactAdmin(model=get_user_model(), admin_site=None)
        self.superuser = create_superuser()
        self.staffuser = create_user()

    def test_readonly_when_restricted_staffuser(self):
        request = self.factory.get("/")
        request.user = self.staffuser

        readonly_fields = self.admin.get_readonly_fields(request)

        expected_fields = [
            "user",
        ]

        self.assertEqual(readonly_fields, expected_fields)

    def test_readonly_when_restricted_superuser(self):
        request = self.factory.get("/")
        request.user = self.superuser

        readonly_fields = self.admin.get_readonly_fields(request)

        expected_fields = []

        self.assertEqual(readonly_fields, expected_fields)

    def tearDown(self):
        User.objects.all().delete()
