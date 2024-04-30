from auditlog.registry import auditlog  # type: ignore
from .contact import Contact
from .domain_request import DomainRequest
from .domain_information import DomainInformation
from .domain import Domain
from .draft_domain import DraftDomain
from .federal_agency import FederalAgency
from .host_ip import HostIP
from .host import Host
from .domain_invitation import DomainInvitation
from .user_domain_role import UserDomainRole
from .public_contact import PublicContact
from .user import User
from .user_group import UserGroup
from .website import Website
from .transition_domain import TransitionDomain
from .verified_by_staff import VerifiedByStaff
from .waffle_flag import WaffleFlag

__all__ = [
    "Contact",
    "DomainRequest",
    "DomainInformation",
    "Domain",
    "DraftDomain",
    "DomainInvitation",
    "FederalAgency",
    "HostIP",
    "Host",
    "UserDomainRole",
    "PublicContact",
    "User",
    "UserGroup",
    "Website",
    "TransitionDomain",
    "VerifiedByStaff",
    "WaffleFlag",
]

auditlog.register(Contact)
auditlog.register(DomainRequest)
auditlog.register(Domain)
auditlog.register(DraftDomain)
auditlog.register(DomainInvitation)
auditlog.register(DomainInformation)
auditlog.register(FederalAgency)
auditlog.register(HostIP)
auditlog.register(Host)
auditlog.register(UserDomainRole)
auditlog.register(PublicContact)
auditlog.register(User, m2m_fields=["user_permissions", "groups"])
auditlog.register(UserGroup, m2m_fields=["permissions"])
auditlog.register(Website)
auditlog.register(TransitionDomain)
auditlog.register(VerifiedByStaff)
auditlog.register(WaffleFlag)
