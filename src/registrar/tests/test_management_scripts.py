import copy
import datetime

from django.test import TestCase

from registrar.models import (
    User,
    Domain,
    DomainInvitation,
    TransitionDomain,
    DomainInformation,
    UserDomainRole,
)

from django.core.management import call_command
from unittest.mock import patch

from .common import MockEppLib


class TestPopulateFirstReady(TestCase):
    """Tests for the populate_first_ready script"""

    def setUp(self):
        """Creates a fake domain object"""
        super().setUp()
        self.ready_domain, _ = Domain.objects.get_or_create(name="fakeready.gov", state=Domain.State.READY)
        self.dns_needed_domain, _ = Domain.objects.get_or_create(name="fakedns.gov", state=Domain.State.DNS_NEEDED)
        self.deleted_domain, _ = Domain.objects.get_or_create(name="fakedeleted.gov", state=Domain.State.DELETED)
        self.hold_domain, _ = Domain.objects.get_or_create(name="fakehold.gov", state=Domain.State.ON_HOLD)
        self.unknown_domain, _ = Domain.objects.get_or_create(name="fakeunknown.gov", state=Domain.State.UNKNOWN)

        # Set a ready_at date for testing purposes
        self.ready_at_date = datetime.date(2022, 12, 31)

    def tearDown(self):
        """Deletes all DB objects related to migrations"""
        super().tearDown()

        # Delete domains
        Domain.objects.all().delete()

    def run_populate_first_ready(self):
        """
        This method executes the populate_first_ready command.

        The 'call_command' function from Django's management framework is then used to
        execute the populate_first_ready command with the specified arguments.
        """
        with patch(
            "registrar.management.commands.utility.terminal_helper.TerminalHelper.query_yes_no_exit",  # noqa
            return_value=True,
        ):
            call_command("populate_first_ready")

    def test_populate_first_ready_state_ready(self):
        """
        Tests that the populate_first_ready works as expected for the state 'ready'
        """
        # Set the created at date
        self.ready_domain.created_at = self.ready_at_date
        self.ready_domain.save()

        desired_domain = copy.deepcopy(self.ready_domain)

        desired_domain.first_ready = self.ready_at_date

        # Run the expiration date script
        self.run_populate_first_ready()

        self.assertEqual(desired_domain, self.ready_domain)

        # Explicitly test the first_ready date
        first_ready = Domain.objects.filter(name="fakeready.gov").get().first_ready
        self.assertEqual(first_ready, self.ready_at_date)

    def test_populate_first_ready_state_deleted(self):
        """
        Tests that the populate_first_ready works as expected for the state 'deleted'
        """
        # Set the created at date
        self.deleted_domain.created_at = self.ready_at_date
        self.deleted_domain.save()

        desired_domain = copy.deepcopy(self.deleted_domain)

        desired_domain.first_ready = self.ready_at_date

        # Run the expiration date script
        self.run_populate_first_ready()

        self.assertEqual(desired_domain, self.deleted_domain)

        # Explicitly test the first_ready date
        first_ready = Domain.objects.filter(name="fakedeleted.gov").get().first_ready
        self.assertEqual(first_ready, self.ready_at_date)

    def test_populate_first_ready_state_dns_needed(self):
        """
        Tests that the populate_first_ready doesn't make changes when a domain's state  is 'dns_needed'
        """
        # Set the created at date
        self.dns_needed_domain.created_at = self.ready_at_date
        self.dns_needed_domain.save()

        desired_domain = copy.deepcopy(self.dns_needed_domain)

        desired_domain.first_ready = None

        # Run the expiration date script
        self.run_populate_first_ready()

        current_domain = self.dns_needed_domain
        # The object should largely be unaltered (does not test first_ready)
        self.assertEqual(desired_domain, current_domain)

        first_ready = Domain.objects.filter(name="fakedns.gov").get().first_ready

        # Explicitly test the first_ready date
        self.assertNotEqual(first_ready, self.ready_at_date)
        self.assertEqual(first_ready, None)

    def test_populate_first_ready_state_on_hold(self):
        """
        Tests that the populate_first_ready works as expected for the state 'on_hold'
        """
        self.hold_domain.created_at = self.ready_at_date
        self.hold_domain.save()

        desired_domain = copy.deepcopy(self.hold_domain)
        desired_domain.first_ready = self.ready_at_date

        # Run the update first ready_at script
        self.run_populate_first_ready()

        current_domain = self.hold_domain
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the first_ready date
        first_ready = Domain.objects.filter(name="fakehold.gov").get().first_ready
        self.assertEqual(first_ready, self.ready_at_date)

    def test_populate_first_ready_state_unknown(self):
        """
        Tests that the populate_first_ready works as expected for the state 'unknown'
        """
        # Set the created at date
        self.unknown_domain.created_at = self.ready_at_date
        self.unknown_domain.save()

        desired_domain = copy.deepcopy(self.unknown_domain)
        desired_domain.first_ready = None

        # Run the expiration date script
        self.run_populate_first_ready()

        current_domain = self.unknown_domain

        # The object should largely be unaltered (does not test first_ready)
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the first_ready date
        first_ready = Domain.objects.filter(name="fakeunknown.gov").get().first_ready
        self.assertNotEqual(first_ready, self.ready_at_date)
        self.assertEqual(first_ready, None)


class TestPatchAgencyInfo(TestCase):
    def setUp(self):
        self.user, _ = User.objects.get_or_create(username="testuser")
        self.domain, _ = Domain.objects.get_or_create(name="testdomain.gov")
        self.domain_info, _ = DomainInformation.objects.get_or_create(domain=self.domain, creator=self.user)
        self.transition_domain, _ = TransitionDomain.objects.get_or_create(
            domain_name="testdomain.gov", federal_agency="test agency"
        )

    def tearDown(self):
        Domain.objects.all().delete()
        DomainInformation.objects.all().delete()
        User.objects.all().delete()
        TransitionDomain.objects.all().delete()

    @patch("registrar.management.commands.utility.terminal_helper.TerminalHelper.query_yes_no_exit", return_value=True)
    def call_patch_federal_agency_info(self, mock_prompt):
        """Calls the patch_federal_agency_info command and mimics a keypress"""
        call_command("patch_federal_agency_info", "registrar/tests/data/fake_current_full.csv", debug=True)

    def test_patch_agency_info(self):
        """
        Tests that the `patch_federal_agency_info` command successfully
        updates the `federal_agency` field
        of a `DomainInformation` object when the corresponding
        `TransitionDomain` object has a valid `federal_agency`.
        """

        # Ensure that the federal_agency is None
        self.assertEqual(self.domain_info.federal_agency, None)

        self.call_patch_federal_agency_info()

        # Reload the domain_info object from the database
        self.domain_info.refresh_from_db()

        # Check that the federal_agency field was updated
        self.assertEqual(self.domain_info.federal_agency, "test agency")

    def test_patch_agency_info_skip(self):
        """
        Tests that the `patch_federal_agency_info` command logs a warning and
        does not update the `federal_agency` field
        of a `DomainInformation` object when the corresponding
        `TransitionDomain` object does not exist.
        """
        # Set federal_agency to None to simulate a skip
        self.transition_domain.federal_agency = None
        self.transition_domain.save()

        with self.assertLogs("registrar.management.commands.patch_federal_agency_info", level="WARNING") as context:
            self.call_patch_federal_agency_info()

        # Check that the correct log message was output
        self.assertIn("SOME AGENCY DATA WAS NONE", context.output[0])

        # Reload the domain_info object from the database
        self.domain_info.refresh_from_db()

        # Check that the federal_agency field was not updated
        self.assertIsNone(self.domain_info.federal_agency)

    def test_patch_agency_info_skip_updates_data(self):
        """
        Tests that the `patch_federal_agency_info` command logs a warning but
        updates the DomainInformation object, because a record exists in the
        provided current-full.csv file.
        """
        # Set federal_agency to None to simulate a skip
        self.transition_domain.federal_agency = None
        self.transition_domain.save()

        # Change the domain name to something parsable in the .csv
        self.domain.name = "cdomain1.gov"
        self.domain.save()

        with self.assertLogs("registrar.management.commands.patch_federal_agency_info", level="WARNING") as context:
            self.call_patch_federal_agency_info()

        # Check that the correct log message was output
        self.assertIn("SOME AGENCY DATA WAS NONE", context.output[0])

        # Reload the domain_info object from the database
        self.domain_info.refresh_from_db()

        # Check that the federal_agency field was not updated
        self.assertEqual(self.domain_info.federal_agency, "World War I Centennial Commission")

    def test_patch_agency_info_skips_valid_domains(self):
        """
        Tests that the `patch_federal_agency_info` command logs INFO and
        does not update the `federal_agency` field
        of a `DomainInformation` object
        """
        self.domain_info.federal_agency = "unchanged"
        self.domain_info.save()

        with self.assertLogs("registrar.management.commands.patch_federal_agency_info", level="INFO") as context:
            self.call_patch_federal_agency_info()

        # Check that the correct log message was output
        self.assertIn("FINISHED", context.output[1])

        # Reload the domain_info object from the database
        self.domain_info.refresh_from_db()

        # Check that the federal_agency field was not updated
        self.assertEqual(self.domain_info.federal_agency, "unchanged")


class TestExtendExpirationDates(MockEppLib):
    def setUp(self):
        """Defines the file name of migration_json and the folder its contained in"""
        super().setUp()
        # Create a valid domain that is updatable
        Domain.objects.get_or_create(
            name="waterbutpurple.gov", state=Domain.State.READY, expiration_date=datetime.date(2023, 11, 15)
        )
        TransitionDomain.objects.get_or_create(
            username="testytester@mail.com",
            domain_name="waterbutpurple.gov",
            epp_expiration_date=datetime.date(2023, 11, 15),
        )
        # Create a domain with an invalid expiration date
        Domain.objects.get_or_create(
            name="fake.gov", state=Domain.State.READY, expiration_date=datetime.date(2022, 5, 25)
        )
        TransitionDomain.objects.get_or_create(
            username="themoonisactuallycheese@mail.com",
            domain_name="fake.gov",
            epp_expiration_date=datetime.date(2022, 5, 25),
        )
        # Create a domain with an invalid state
        Domain.objects.get_or_create(
            name="fakeneeded.gov", state=Domain.State.DNS_NEEDED, expiration_date=datetime.date(2023, 11, 15)
        )
        TransitionDomain.objects.get_or_create(
            username="fakeneeded@mail.com",
            domain_name="fakeneeded.gov",
            epp_expiration_date=datetime.date(2023, 11, 15),
        )
        # Create a domain with a date greater than the maximum
        Domain.objects.get_or_create(
            name="fakemaximum.gov", state=Domain.State.READY, expiration_date=datetime.date(2024, 12, 31)
        )
        TransitionDomain.objects.get_or_create(
            username="fakemaximum@mail.com",
            domain_name="fakemaximum.gov",
            epp_expiration_date=datetime.date(2024, 12, 31),
        )

    def tearDown(self):
        """Deletes all DB objects related to migrations"""
        super().tearDown()
        # Delete domain information
        Domain.objects.all().delete()
        DomainInformation.objects.all().delete()
        DomainInvitation.objects.all().delete()
        TransitionDomain.objects.all().delete()

        # Delete users
        User.objects.all().delete()
        UserDomainRole.objects.all().delete()

    def run_extend_expiration_dates(self):
        """
        This method executes the extend_expiration_dates command.

        The 'call_command' function from Django's management framework is then used to
        execute the extend_expiration_dates command with the specified arguments.
        """
        with patch(
            "registrar.management.commands.utility.terminal_helper.TerminalHelper.query_yes_no_exit",  # noqa
            return_value=True,
        ):
            call_command("extend_expiration_dates")

    def test_extends_expiration_date_correctly(self):
        """
        Tests that the extend_expiration_dates method extends dates as expected
        """
        desired_domain = Domain.objects.filter(name="waterbutpurple.gov").get()
        desired_domain.expiration_date = datetime.date(2024, 11, 15)

        # Run the expiration date script
        self.run_extend_expiration_dates()

        current_domain = Domain.objects.filter(name="waterbutpurple.gov").get()

        self.assertEqual(desired_domain, current_domain)
        # Explicitly test the expiration date
        self.assertEqual(current_domain.expiration_date, datetime.date(2024, 11, 15))

    def test_extends_expiration_date_skips_non_current(self):
        """
        Tests that the extend_expiration_dates method correctly skips domains
        with an expiration date less than a certain threshold.
        """
        desired_domain = Domain.objects.filter(name="fake.gov").get()
        desired_domain.expiration_date = datetime.date(2022, 5, 25)

        # Run the expiration date script
        self.run_extend_expiration_dates()

        current_domain = Domain.objects.filter(name="fake.gov").get()
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the expiration date. The extend_expiration_dates script
        # will skip all dates less than date(2023, 11, 15), meaning that this domain
        # should not be affected by the change.
        self.assertEqual(current_domain.expiration_date, datetime.date(2022, 5, 25))

    def test_extends_expiration_date_skips_maximum_date(self):
        """
        Tests that the extend_expiration_dates method correctly skips domains
        with an expiration date more than a certain threshold.
        """
        desired_domain = Domain.objects.filter(name="fakemaximum.gov").get()
        desired_domain.expiration_date = datetime.date(2024, 12, 31)

        # Run the expiration date script
        self.run_extend_expiration_dates()

        current_domain = Domain.objects.filter(name="fakemaximum.gov").get()
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the expiration date. The extend_expiration_dates script
        # will skip all dates less than date(2023, 11, 15), meaning that this domain
        # should not be affected by the change.
        self.assertEqual(current_domain.expiration_date, datetime.date(2024, 12, 31))

    def test_extends_expiration_date_skips_non_ready(self):
        """
        Tests that the extend_expiration_dates method correctly skips domains not in the state "ready"
        """
        desired_domain = Domain.objects.filter(name="fakeneeded.gov").get()
        desired_domain.expiration_date = datetime.date(2023, 11, 15)

        # Run the expiration date script
        self.run_extend_expiration_dates()

        current_domain = Domain.objects.filter(name="fakeneeded.gov").get()
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the expiration date. The extend_expiration_dates script
        # will skip all dates less than date(2023, 11, 15), meaning that this domain
        # should not be affected by the change.
        self.assertEqual(current_domain.expiration_date, datetime.date(2023, 11, 15))

    def test_extends_expiration_date_idempotent(self):
        """
        Tests the idempotency of the extend_expiration_dates command.

        Verifies that running the method multiple times does not change the expiration date
        of a domain beyond the initial extension.
        """
        desired_domain = Domain.objects.filter(name="waterbutpurple.gov").get()
        desired_domain.expiration_date = datetime.date(2024, 11, 15)

        # Run the expiration date script
        self.run_extend_expiration_dates()

        current_domain = Domain.objects.filter(name="waterbutpurple.gov").get()
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the expiration date
        self.assertEqual(desired_domain.expiration_date, datetime.date(2024, 11, 15))

        # Run the expiration date script again
        self.run_extend_expiration_dates()

        # The old domain shouldn't have changed
        self.assertEqual(desired_domain, current_domain)

        # Explicitly test the expiration date - should be the same
        self.assertEqual(desired_domain.expiration_date, datetime.date(2024, 11, 15))
