from auditlog.registry import auditlog  # type: ignore
from .contact import Contact
from .domain_application import DomainApplication
from .domain_information import DomainInformation
from .domain import Domain
from .draft_domain import DraftDomain
from .host_ip import HostIP
from .host import Host
from .domain_invitation import DomainInvitation
from .nameserver import Nameserver
from .user_domain_role import UserDomainRole
from .public_contact import PublicContact
from .user import User
from .user_group import UserGroup
from .website import Website
from .transition_domain import TransitionDomain

__all__ = [
    "Contact",
    "DomainApplication",
    "DomainInformation",
    "Domain",
    "DraftDomain",
    "DomainInvitation",
    "HostIP",
    "Host",
    "Nameserver",
    "UserDomainRole",
    "PublicContact",
    "User",
    "UserGroup",
    "Website",
    "TransitionDomain",
]

auditlog.register(Contact)
auditlog.register(DomainApplication)
auditlog.register(Domain)
auditlog.register(DraftDomain)
auditlog.register(DomainInvitation)
auditlog.register(DomainInformation)
auditlog.register(HostIP)
auditlog.register(Host)
auditlog.register(Nameserver)
auditlog.register(UserDomainRole)
auditlog.register(PublicContact)
auditlog.register(User, m2m_fields=["user_permissions", "groups"])
auditlog.register(UserGroup, m2m_fields=["permissions"])
auditlog.register(Website)
auditlog.register(TransitionDomain)
