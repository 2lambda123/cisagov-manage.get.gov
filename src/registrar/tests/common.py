import datetime
import os
import logging

from contextlib import contextmanager
import random
from string import ascii_uppercase
from django.test import TestCase
from unittest.mock import MagicMock, Mock, patch
from typing import List, Dict

from django.conf import settings
from django.contrib.auth import get_user_model, login

from registrar.models import (
    Contact,
    DraftDomain,
    Website,
    DomainApplication,
    DomainInvitation,
    User,
    UserGroup,
    DomainInformation,
    PublicContact,
    Domain,
)
from epplibwrapper import (
    commands,
    common,
    extensions,
    info,
    RegistryError,
    ErrorCode,
    responses,
)

from registrar.models.utility.contact_error import ContactError, ContactErrorCodes

logger = logging.getLogger(__name__)


def get_handlers():
    """Obtain pointers to all StreamHandlers."""
    handlers = {}

    rootlogger = logging.getLogger()
    for h in rootlogger.handlers:
        if isinstance(h, logging.StreamHandler):
            handlers[h.name] = h

    for logger in logging.Logger.manager.loggerDict.values():
        if not isinstance(logger, logging.PlaceHolder):
            for h in logger.handlers:
                if isinstance(h, logging.StreamHandler):
                    handlers[h.name] = h

    return handlers


@contextmanager
def less_console_noise():
    """
    Context manager to use in tests to silence console logging.

    This is helpful on tests which trigger console messages
    (such as errors) which are normal and expected.

    It can easily be removed to debug a failing test.
    """
    restore = {}
    handlers = get_handlers()
    devnull = open(os.devnull, "w")

    # redirect all the streams
    for handler in handlers.values():
        prior = handler.setStream(devnull)
        restore[handler.name] = prior
    try:
        # run the test
        yield
    finally:
        # restore the streams
        for handler in handlers.values():
            handler.setStream(restore[handler.name])
        # close the file we opened
        devnull.close()


class MockUserLogin:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_anonymous:
            user = None
            UserModel = get_user_model()
            username = "Testy"
            args = {
                UserModel.USERNAME_FIELD: username,
            }
            user, _ = UserModel.objects.get_or_create(**args)
            user.is_staff = True
            # Create or retrieve the group
            group, _ = UserGroup.objects.get_or_create(name="full_access_group")
            # Add the user to the group
            user.groups.set([group])
            user.save()
            backend = settings.AUTHENTICATION_BACKENDS[-1]
            login(request, user, backend=backend)

        response = self.get_response(request)
        return response


class MockSESClient(Mock):
    EMAILS_SENT: List[Dict] = []

    def send_email(self, *args, **kwargs):
        self.EMAILS_SENT.append({"args": args, "kwargs": kwargs})


class AuditedAdminMockData:
    """Creates simple data mocks for AuditedAdminTest.
    Can likely be more generalized, but the primary purpose of this class is to simplify
    mock data creation, especially for lists of items,
    by making the assumption that for most use cases we don't have to worry about
    data 'accuracy' ('testy 2' is not an accurate first_name for example), we just care about
    implementing some kind of patterning, especially with lists of items.

    Two variables are used across multiple functions:

    *item_name* - Used in patterning. Will be appended en masse to multiple str fields,
    like first_name. For example, item_name 'egg' will return a user object of:

    first_name: 'egg first_name:user',
    last_name: 'egg last_name:user',
    username: 'egg username:user'

    where 'user' is the short_hand

    *short_hand* - Used in patterning. Certain fields will have ':{shorthand}' appended to it,
    as a way to optionally include metadata in the str itself. Can be further expanded on.
    Came from a bug where different querysets used in testing would effectively be 'anonymized', wherein
    it would only display a list of types, but not include the variable name.
    """  # noqa

    # Constants for different domain object types
    INFORMATION = "information"
    APPLICATION = "application"
    INVITATION = "invitation"

    def dummy_user(self, item_name, short_hand):
        """Creates a dummy user object,
        but with a shorthand and support for multiple"""
        user = User.objects.get_or_create(
            first_name="{} first_name:{}".format(item_name, short_hand),
            last_name="{} last_name:{}".format(item_name, short_hand),
            username="{} username:{}".format(item_name, short_hand),
        )[0]
        return user

    def dummy_contact(self, item_name, short_hand):
        """Creates a dummy contact object"""
        contact = Contact.objects.get_or_create(
            first_name="{} first_name:{}".format(item_name, short_hand),
            last_name="{} last_name:{}".format(item_name, short_hand),
            title="{} title:{}".format(item_name, short_hand),
            email="{}testy@town.com".format(item_name),
            phone="(555) 555 5555",
        )[0]
        return contact

    def dummy_draft_domain(self, item_name, prebuilt=False):
        """
        Creates a dummy DraftDomain object
        Args:
            item_name (str): Value for 'name' in a DraftDomain object.
            prebuilt (boolean): Determines return type.
        Returns:
            DraftDomain: Where name = 'item_name'. If prebuilt = True, then
            name will be "city{}.gov".format(item_name).
        """
        if prebuilt:
            item_name = "city{}.gov".format(item_name)
        return DraftDomain.objects.get_or_create(name=item_name)[0]

    def dummy_domain(self, item_name, prebuilt=False):
        """
        Creates a dummy domain object
        Args:
            item_name (str): Value for 'name' in a Domain object.
            prebuilt (boolean): Determines return type.
        Returns:
            Domain: Where name = 'item_name'. If prebuilt = True, then
            domain name will be "city{}.gov".format(item_name).
        """
        if prebuilt:
            item_name = "city{}.gov".format(item_name)
        return Domain.objects.get_or_create(name=item_name)[0]

    def dummy_website(self, item_name):
        """
        Creates a dummy website object
        Args:
            item_name (str): Value for 'website' in a Website object.
        Returns:
            Website: Where website = 'item_name'.
        """
        return Website.objects.get_or_create(website=item_name)[0]

    def dummy_alt(self, item_name):
        """
        Creates a dummy website object for alternates
        Args:
            item_name (str): Value for 'website' in a Website object.
        Returns:
            Website: Where website = "cityalt{}.gov".format(item_name).
        """
        return self.dummy_website(item_name="cityalt{}.gov".format(item_name))

    def dummy_current(self, item_name):
        """
        Creates a dummy website object for current
        Args:
            item_name (str): Value for 'website' in a Website object.
            prebuilt (boolean): Determines return type.
        Returns:
            Website: Where website = "city{}.gov".format(item_name)
        """
        return self.dummy_website(item_name="city{}.com".format(item_name))

    def get_common_domain_arg_dictionary(
        self,
        item_name,
        org_type="federal",
        federal_type="executive",
        purpose="Purpose of the site",
    ):
        """
        Generates a generic argument dict for most domains
        Args:
            item_name (str): A shared str value appended to first_name, last_name,
            organization_name, address_line1, address_line2,
            title, email, and username.

            org_type (str - optional): Sets a domains org_type

            federal_type (str - optional): Sets a domains federal_type

            purpose (str - optional): Sets a domains purpose
        Returns:
            Dictionary: {
                organization_type: str,
                federal_type: str,
                purpose: str,
                organization_name: str = "{} organization".format(item_name),
                address_line1: str = "{} address_line1".format(item_name),
                address_line2: str = "{} address_line2".format(item_name),
                is_policy_acknowledged: boolean = True,
                state_territory: str = "NY",
                zipcode: str = "10002",
                about_your_organization: str = "e-Government",
                anything_else: str = "There is more",
                authorizing_official: Contact = self.dummy_contact(item_name, "authorizing_official"),
                submitter: Contact = self.dummy_contact(item_name, "submitter"),
                creator: User = self.dummy_user(item_name, "creator"),
            }
        """  # noqa
        common_args = dict(
            organization_type=org_type,
            federal_type=federal_type,
            purpose=purpose,
            organization_name="{} organization".format(item_name),
            address_line1="{} address_line1".format(item_name),
            address_line2="{} address_line2".format(item_name),
            is_policy_acknowledged=True,
            state_territory="NY",
            zipcode="10002",
            about_your_organization="e-Government",
            anything_else="There is more",
            authorizing_official=self.dummy_contact(item_name, "authorizing_official"),
            submitter=self.dummy_contact(item_name, "submitter"),
            creator=self.dummy_user(item_name, "creator"),
        )
        return common_args

    def dummy_kwarg_boilerplate(
        self,
        domain_type,
        item_name,
        status=DomainApplication.STARTED,
        org_type="federal",
        federal_type="executive",
        purpose="Purpose of the site",
    ):
        """
        Returns a prebuilt kwarg dictionary for DomainApplication,
        DomainInformation, or DomainInvitation.
        Args:
            domain_type (str): is either 'application', 'information',
            or 'invitation'.

            item_name (str): A shared str value appended to first_name, last_name,
            organization_name, address_line1, address_line2,
            title, email, and username.

            status (str - optional): Defines the status for DomainApplication,
            e.g. DomainApplication.STARTED

            org_type (str - optional): Sets a domains org_type

            federal_type (str - optional): Sets a domains federal_type

            purpose (str - optional): Sets a domains purpose
        Returns:
            dict: Returns a dictionary structurally consistent with the expected input
            of either DomainApplication, DomainInvitation, or DomainInformation
            based on the 'domain_type' field.
        """  # noqa
        common_args = self.get_common_domain_arg_dictionary(
            item_name, org_type, federal_type, purpose
        )
        full_arg_dict = None
        match domain_type:
            case self.APPLICATION:
                full_arg_dict = dict(
                    **common_args,
                    requested_domain=self.dummy_draft_domain(item_name),
                    investigator=self.dummy_user(item_name, "investigator"),
                    status=status,
                )
            case self.INFORMATION:
                domain_app = self.create_full_dummy_domain_application(item_name)
                full_arg_dict = dict(
                    **common_args,
                    domain=self.dummy_domain(item_name, True),
                    domain_application=domain_app,
                )
            case self.INVITATION:
                full_arg_dict = dict(
                    email="test_mail@mail.com",
                    domain=self.dummy_domain(item_name, True),
                    status=DomainInvitation.INVITED,
                )
        return full_arg_dict

    def create_full_dummy_domain_application(
        self, item_name, status=DomainApplication.STARTED
    ):
        """Creates a dummy domain application object"""
        domain_application_kwargs = self.dummy_kwarg_boilerplate(
            self.APPLICATION, item_name, status
        )
        application = DomainApplication.objects.get_or_create(
            **domain_application_kwargs
        )[0]
        return application

    def create_full_dummy_domain_information(
        self, item_name, status=DomainApplication.STARTED
    ):
        """Creates a dummy domain information object"""
        domain_application_kwargs = self.dummy_kwarg_boilerplate(
            self.INFORMATION, item_name, status
        )
        application = DomainInformation.objects.get_or_create(
            **domain_application_kwargs
        )[0]
        return application

    def create_full_dummy_domain_invitation(
        self, item_name, status=DomainApplication.STARTED
    ):
        """Creates a dummy domain invitation object"""
        domain_application_kwargs = self.dummy_kwarg_boilerplate(
            self.INVITATION, item_name, status
        )
        application = DomainInvitation.objects.get_or_create(
            **domain_application_kwargs
        )[0]

        return application

    def create_full_dummy_domain_object(
        self,
        domain_type,
        item_name,
        has_other_contacts=True,
        has_current_website=True,
        has_alternative_gov_domain=True,
        status=DomainApplication.STARTED,
    ):
        """A helper to create a dummy domain application object"""
        application = None
        match domain_type:
            case self.APPLICATION:
                application = self.create_full_dummy_domain_application(
                    item_name, status
                )
            case self.INVITATION:
                application = self.create_full_dummy_domain_invitation(
                    item_name, status
                )
            case self.INFORMATION:
                application = self.create_full_dummy_domain_information(
                    item_name, status
                )
            case _:
                raise ValueError("Invalid domain_type, must conform to given constants")

        if has_other_contacts and domain_type != self.INVITATION:
            other = self.dummy_contact(item_name, "other")
            application.other_contacts.add(other)
        if has_current_website and domain_type == self.APPLICATION:
            current = self.dummy_current(item_name)
            application.current_websites.add(current)
        if has_alternative_gov_domain and domain_type == self.APPLICATION:
            alt = self.dummy_alt(item_name)
            application.alternative_domains.add(alt)

        return application


def mock_user():
    """A simple user."""
    user_kwargs = dict(
        id=4,
        first_name="Rachid",
        last_name="Mrad",
    )
    mock_user, _ = User.objects.get_or_create(**user_kwargs)
    return mock_user


def create_superuser():
    User = get_user_model()
    p = "adminpass"
    user = User.objects.create_user(
        username="superuser",
        email="admin@example.com",
        is_staff=True,
        password=p,
    )
    # Retrieve the group or create it if it doesn't exist
    group, _ = UserGroup.objects.get_or_create(name="full_access_group")
    # Add the user to the group
    user.groups.set([group])
    return user


def create_user():
    User = get_user_model()
    p = "userpass"
    user = User.objects.create_user(
        username="staffuser",
        email="user@example.com",
        is_staff=True,
        password=p,
    )
    # Retrieve the group or create it if it doesn't exist
    group, _ = UserGroup.objects.get_or_create(name="cisa_analysts_group")
    # Add the user to the group
    user.groups.set([group])
    return user


def create_ready_domain():
    domain, _ = Domain.objects.get_or_create(name="city.gov", state=Domain.State.READY)
    return domain


def completed_application(
    has_other_contacts=True,
    has_current_website=True,
    has_alternative_gov_domain=True,
    has_about_your_organization=True,
    has_anything_else=True,
    status=DomainApplication.STARTED,
    user=False,
    name="city.gov",
):
    """A completed domain application."""
    if not user:
        user = get_user_model().objects.create(username="username")
    ao, _ = Contact.objects.get_or_create(
        first_name="Testy",
        last_name="Tester",
        title="Chief Tester",
        email="testy@town.com",
        phone="(555) 555 5555",
    )
    domain, _ = DraftDomain.objects.get_or_create(name=name)
    alt, _ = Website.objects.get_or_create(website="city1.gov")
    current, _ = Website.objects.get_or_create(website="city.com")
    you, _ = Contact.objects.get_or_create(
        first_name="Testy2",
        last_name="Tester2",
        title="Admin Tester",
        email="mayor@igorville.gov",
        phone="(555) 555 5556",
    )
    other, _ = Contact.objects.get_or_create(
        first_name="Testy",
        last_name="Tester",
        title="Another Tester",
        email="testy2@town.com",
        phone="(555) 555 5557",
    )
    domain_application_kwargs = dict(
        organization_type="federal",
        federal_type="executive",
        purpose="Purpose of the site",
        is_policy_acknowledged=True,
        organization_name="Testorg",
        address_line1="address 1",
        address_line2="address 2",
        state_territory="NY",
        zipcode="10002",
        authorizing_official=ao,
        requested_domain=domain,
        submitter=you,
        creator=user,
        status=status,
    )
    if has_about_your_organization:
        domain_application_kwargs["about_your_organization"] = "e-Government"
    if has_anything_else:
        domain_application_kwargs["anything_else"] = "There is more"

    application, _ = DomainApplication.objects.get_or_create(
        **domain_application_kwargs
    )

    if has_other_contacts:
        application.other_contacts.add(other)
    if has_current_website:
        application.current_websites.add(current)
    if has_alternative_gov_domain:
        application.alternative_domains.add(alt)

    return application


def multiple_unalphabetical_domain_objects(
    domain_type=AuditedAdminMockData.APPLICATION,
):
    """Returns a list of generic domain objects for testing purposes"""
    applications = []
    list_of_letters = list(ascii_uppercase)
    random.shuffle(list_of_letters)

    mock = AuditedAdminMockData()
    for object_name in list_of_letters:
        application = mock.create_full_dummy_domain_object(domain_type, object_name)
        applications.append(application)
    return applications


def generic_domain_object(domain_type, object_name):
    """Returns a generic domain object of
    domain_type 'application', 'information', or 'invitation'"""
    mock = AuditedAdminMockData()
    application = mock.create_full_dummy_domain_object(domain_type, object_name)
    return application


class MockEppLib(TestCase):
    class fakedEppObject(object):
        """"""

        def __init__(
            self,
            auth_info=...,
            cr_date=...,
            contacts=...,
            hosts=...,
            statuses=...,
            avail=...,
            addrs=...,
            registrant=...,
        ):
            self.auth_info = auth_info
            self.cr_date = cr_date
            self.contacts = contacts
            self.hosts = hosts
            self.statuses = statuses
            self.avail = avail  # use for CheckDomain
            self.addrs = addrs
            self.registrant = registrant

        def dummyInfoContactResultData(
            self,
            id,
            email,
            cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
            pw="thisisnotapassword",
        ):
            fake = info.InfoContactResultData(
                id=id,
                postal_info=common.PostalInfo(
                    name="Registry Customer Service",
                    addr=common.ContactAddr(
                        street=["4200 Wilson Blvd."],
                        city="Arlington",
                        pc="22201",
                        cc="US",
                        sp="VA",
                    ),
                    org="Cybersecurity and Infrastructure Security Agency",
                    type="type",
                ),
                voice="+1.8882820870",
                fax="+1-212-9876543",
                email=email,
                auth_info=common.ContactAuthInfo(pw=pw),
                roid=...,
                statuses=[],
                cl_id=...,
                cr_id=...,
                cr_date=cr_date,
                up_id=...,
                up_date=...,
                tr_date=...,
                disclose=...,
                vat=...,
                ident=...,
                notify_email=...,
            )
            return fake

    mockDataInfoDomain = fakedEppObject(
        "fakePw",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[
            common.DomainContact(
                contact="123", type=PublicContact.ContactTypeChoices.SECURITY
            )
        ],
        hosts=["fake.host.com"],
        statuses=[
            common.Status(state="serverTransferProhibited", description="", lang="en"),
            common.Status(state="inactive", description="", lang="en"),
        ],
    )
    mockDataInfoContact = mockDataInfoDomain.dummyInfoContactResultData(
        "123", "123@mail.gov", datetime.datetime(2023, 5, 25, 19, 45, 35), "lastPw"
    )
    InfoDomainWithContacts = fakedEppObject(
        "fakepw",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[
            common.DomainContact(
                contact="securityContact",
                type=PublicContact.ContactTypeChoices.SECURITY,
            ),
            common.DomainContact(
                contact="technicalContact",
                type=PublicContact.ContactTypeChoices.TECHNICAL,
            ),
            common.DomainContact(
                contact="adminContact",
                type=PublicContact.ContactTypeChoices.ADMINISTRATIVE,
            ),
        ],
        hosts=["fake.host.com"],
        statuses=[
            common.Status(state="serverTransferProhibited", description="", lang="en"),
            common.Status(state="inactive", description="", lang="en"),
        ],
        registrant="regContact",
    )

    InfoDomainWithDefaultSecurityContact = fakedEppObject(
        "fakepw",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[
            common.DomainContact(
                contact="defaultSec",
                type=PublicContact.ContactTypeChoices.SECURITY,
            )
        ],
        hosts=["fake.host.com"],
        statuses=[
            common.Status(state="serverTransferProhibited", description="", lang="en"),
            common.Status(state="inactive", description="", lang="en"),
        ],
    )

    InfoDomainWithDefaultTechnicalContact = fakedEppObject(
        "fakepw",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[
            common.DomainContact(
                contact="defaultTech",
                type=PublicContact.ContactTypeChoices.TECHNICAL,
            )
        ],
        hosts=["fake.host.com"],
        statuses=[
            common.Status(state="serverTransferProhibited", description="", lang="en"),
            common.Status(state="inactive", description="", lang="en"),
        ],
    )

    mockDefaultTechnicalContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "defaultTech", "dotgov@cisa.dhs.gov"
    )
    mockDefaultSecurityContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "defaultSec", "dotgov@cisa.dhs.gov"
    )
    mockSecurityContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "securityContact", "security@mail.gov"
    )
    mockTechnicalContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "technicalContact", "tech@mail.gov"
    )
    mockAdministrativeContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "adminContact", "admin@mail.gov"
    )
    mockRegistrantContact = InfoDomainWithContacts.dummyInfoContactResultData(
        "regContact", "registrant@mail.gov"
    )

    infoDomainNoContact = fakedEppObject(
        "security",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=["fake.host.com"],
    )

    infoDomainThreeHosts = fakedEppObject(
        "my-nameserver.gov",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=[
            "ns1.my-nameserver-1.com",
            "ns1.my-nameserver-2.com",
            "ns1.cats-are-superior3.com",
        ],
    )
    infoDomainNoHost = fakedEppObject(
        "my-nameserver.gov",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=[],
    )

    infoDomainTwoHosts = fakedEppObject(
        "my-nameserver.gov",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=["ns1.my-nameserver-1.com", "ns1.my-nameserver-2.com"],
    )

    mockDataInfoHosts = fakedEppObject(
        "lastPw",
        cr_date=datetime.datetime(2023, 8, 25, 19, 45, 35),
        addrs=["1.2.3.4", "2.3.4.5"],
    )

    mockDataHostChange = fakedEppObject(
        "lastPw", cr_date=datetime.datetime(2023, 8, 25, 19, 45, 35)
    )
    addDsData1 = {
        "keyTag": 1234,
        "alg": 3,
        "digestType": 1,
        "digest": "ec0bdd990b39feead889f0ba613db4adec0bdd99",
    }
    addDsData2 = {
        "keyTag": 2345,
        "alg": 3,
        "digestType": 1,
        "digest": "ec0bdd990b39feead889f0ba613db4adecb4adec",
    }
    keyDataDict = {
        "flags": 257,
        "protocol": 3,
        "alg": 1,
        "pubKey": "AQPJ////4Q==",
    }
    dnssecExtensionWithDsData = extensions.DNSSECExtension(
        **{
            "dsData": [
                common.DSData(**addDsData1)  # type: ignore
            ],  # type: ignore
        }
    )
    dnssecExtensionWithMultDsData = extensions.DNSSECExtension(
        **{
            "dsData": [
                common.DSData(**addDsData1),  # type: ignore
                common.DSData(**addDsData2),  # type: ignore
            ],  # type: ignore
        }
    )
    dnssecExtensionWithKeyData = extensions.DNSSECExtension(
        **{
            "keyData": [common.DNSSECKeyData(**keyDataDict)],  # type: ignore
        }
    )
    dnssecExtensionRemovingDsData = extensions.DNSSECExtension()

    infoDomainHasIP = fakedEppObject(
        "nameserverwithip.gov",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=[
            "ns1.nameserverwithip.gov",
            "ns2.nameserverwithip.gov",
            "ns3.nameserverwithip.gov",
        ],
        addrs=["1.2.3.4", "2.3.4.5"],
    )

    infoDomainCheckHostIPCombo = fakedEppObject(
        "nameserversubdomain.gov",
        cr_date=datetime.datetime(2023, 5, 25, 19, 45, 35),
        contacts=[],
        hosts=[
            "ns1.nameserversubdomain.gov",
            "ns2.nameserversubdomain.gov",
        ],
    )

    def _mockDomainName(self, _name, _avail=False):
        return MagicMock(
            res_data=[
                responses.check.CheckDomainResultData(
                    name=_name, avail=_avail, reason=None
                ),
            ]
        )

    def mockCheckDomainCommand(self, _request, cleaned):
        if "gsa.gov" in getattr(_request, "names", None):
            return self._mockDomainName("gsa.gov", True)
        elif "GSA.gov" in getattr(_request, "names", None):
            return self._mockDomainName("GSA.gov", True)
        elif "igorvilleremixed.gov" in getattr(_request, "names", None):
            return self._mockDomainName("igorvilleremixed.gov", False)
        elif "errordomain.gov" in getattr(_request, "names", None):
            raise RegistryError("Registry cannot find domain availability.")
        else:
            return self._mockDomainName("domainnotfound.gov", False)

    def mockSend(self, _request, cleaned):
        """Mocks the registry.send function used inside of domain.py
        registry is imported from epplibwrapper
        returns objects that simulate what would be in a epp response
        but only relevant pieces for tests"""

        match type(_request):
            case commands.InfoDomain:
                return self.mockInfoDomainCommands(_request, cleaned)
            case commands.InfoContact:
                return self.mockInfoContactCommands(_request, cleaned)
            case commands.CreateContact:
                return self.mockCreateContactCommands(_request, cleaned)
            case commands.UpdateDomain:
                return self.mockUpdateDomainCommands(_request, cleaned)
            case commands.CreateHost:
                return MagicMock(
                    res_data=[self.mockDataHostChange],
                    code=ErrorCode.COMMAND_COMPLETED_SUCCESSFULLY,
                )
            case commands.UpdateHost:
                return MagicMock(
                    res_data=[self.mockDataHostChange],
                    code=ErrorCode.COMMAND_COMPLETED_SUCCESSFULLY,
                )
            case commands.DeleteHost:
                return MagicMock(
                    res_data=[self.mockDataHostChange],
                    code=ErrorCode.COMMAND_COMPLETED_SUCCESSFULLY,
                )
            case commands.CheckDomain:
                return self.mockCheckDomainCommand(_request, cleaned)
            case commands.DeleteDomain:
                return self.mockDeleteDomainCommands(_request, cleaned)
            case _:
                return MagicMock(res_data=[self.mockDataInfoHosts])

    def mockUpdateDomainCommands(self, _request, cleaned):
        if getattr(_request, "name", None) == "dnssec-invalid.gov":
            raise RegistryError(code=ErrorCode.PARAMETER_VALUE_RANGE_ERROR)
        else:
            return MagicMock(
                res_data=[self.mockDataHostChange],
                code=ErrorCode.COMMAND_COMPLETED_SUCCESSFULLY,
            )

    def mockDeleteDomainCommands(self, _request, cleaned):
        if getattr(_request, "name", None) == "failDelete.gov":
            name = getattr(_request, "name", None)
            fake_nameserver = "ns1.failDelete.gov"
            if name in fake_nameserver:
                raise RegistryError(
                    code=ErrorCode.OBJECT_ASSOCIATION_PROHIBITS_OPERATION
                )
        return None

    def mockInfoDomainCommands(self, _request, cleaned):
        request_name = getattr(_request, "name", None)

        # Define a dictionary to map request names to data and extension values
        request_mappings = {
            "security.gov": (self.infoDomainNoContact, None),
            "dnssec-dsdata.gov": (
                self.mockDataInfoDomain,
                self.dnssecExtensionWithDsData,
            ),
            "dnssec-multdsdata.gov": (
                self.mockDataInfoDomain,
                self.dnssecExtensionWithMultDsData,
            ),
            "dnssec-keydata.gov": (
                self.mockDataInfoDomain,
                self.dnssecExtensionWithKeyData,
            ),
            "dnssec-none.gov": (self.mockDataInfoDomain, None),
            "my-nameserver.gov": (
                self.infoDomainTwoHosts
                if self.mockedSendFunction.call_count == 5
                else self.infoDomainNoHost,
                None,
            ),
            "nameserverwithip.gov": (self.infoDomainHasIP, None),
            "namerserversubdomain.gov": (self.infoDomainCheckHostIPCombo, None),
            "freeman.gov": (self.InfoDomainWithContacts, None),
            "threenameserversDomain.gov": (self.infoDomainThreeHosts, None),
            "defaultsecurity.gov": (self.InfoDomainWithDefaultSecurityContact, None),
            "defaulttechnical.gov": (self.InfoDomainWithDefaultTechnicalContact, None),
        }

        # Retrieve the corresponding values from the dictionary
        res_data, extensions = request_mappings.get(
            request_name, (self.mockDataInfoDomain, None)
        )

        return MagicMock(
            res_data=[res_data],
            extensions=[extensions] if extensions is not None else [],
        )

    def mockInfoContactCommands(self, _request, cleaned):
        mocked_result: info.InfoContactResultData

        # For testing contact types
        match getattr(_request, "id", None):
            case "securityContact":
                mocked_result = self.mockSecurityContact
            case "technicalContact":
                mocked_result = self.mockTechnicalContact
            case "adminContact":
                mocked_result = self.mockAdministrativeContact
            case "regContact":
                mocked_result = self.mockRegistrantContact
            case "defaultSec":
                mocked_result = self.mockDefaultSecurityContact
            case "defaultTech":
                mocked_result = self.mockDefaultTechnicalContact
            case _:
                # Default contact return
                mocked_result = self.mockDataInfoContact

        return MagicMock(res_data=[mocked_result])

    def mockCreateContactCommands(self, _request, cleaned):
        if (
            getattr(_request, "id", None) == "fail"
            and self.mockedSendFunction.call_count == 3
        ):
            # use this for when a contact is being updated
            # sets the second send() to fail
            raise RegistryError(code=ErrorCode.OBJECT_EXISTS)
        elif getattr(_request, "email", None) == "test@failCreate.gov":
            # use this for when a contact is being updated
            # mocks a registry error on creation
            raise RegistryError(code=None)
        elif getattr(_request, "email", None) == "test@contactError.gov":
            # use this for when a contact is being updated
            # mocks a contact error on creation
            raise ContactError(code=ContactErrorCodes.CONTACT_TYPE_NONE)
        return MagicMock(res_data=[self.mockDataInfoHosts])

    def setUp(self):
        """mock epp send function as this will fail locally"""
        self.mockSendPatch = patch("registrar.models.domain.registry.send")
        self.mockedSendFunction = self.mockSendPatch.start()
        self.mockedSendFunction.side_effect = self.mockSend

    def _convertPublicContactToEpp(
        self, contact: PublicContact, disclose_email=False, createContact=True
    ):
        DF = common.DiscloseField
        fields = {DF.EMAIL}

        di = common.Disclose(
            flag=disclose_email,
            fields=fields,
        )

        # check docs here looks like we may have more than one address field but
        addr = common.ContactAddr(
            [
                getattr(contact, street)
                for street in ["street1", "street2", "street3"]
                if hasattr(contact, street)
            ],  # type: ignore
            city=contact.city,
            pc=contact.pc,
            cc=contact.cc,
            sp=contact.sp,
        )  # type: ignore

        pi = common.PostalInfo(
            name=contact.name,
            addr=addr,
            org=contact.org,
            type="loc",
        )

        ai = common.ContactAuthInfo(pw="2fooBAR123fooBaz")
        if createContact:
            return commands.CreateContact(
                id=contact.registry_id,
                postal_info=pi,  # type: ignore
                email=contact.email,
                voice=contact.voice,
                fax=contact.fax,
                auth_info=ai,
                disclose=di,
                vat=None,
                ident=None,
                notify_email=None,
            )  # type: ignore
        else:
            return commands.UpdateContact(
                id=contact.registry_id,
                postal_info=pi,
                email=contact.email,
                voice=contact.voice,
                fax=contact.fax,
            )

    def tearDown(self):
        self.mockSendPatch.stop()
