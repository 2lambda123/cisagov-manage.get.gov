"""Permissions-related mixin classes."""

from django.contrib.auth.mixins import PermissionRequiredMixin

from registrar.models import (
    Domain,
    DomainApplication,
    DomainInvitation,
    DomainInformation,
    UserDomainRole,
)
import logging


logger = logging.getLogger(__name__)


class OrderableFieldsMixin:
    """
    Mixin to add multi-field ordering capabilities to a Django ModelAdmin on admin_order_field.
    """
    orderable_fk_fields = []

    def __new__(cls, *args, **kwargs):
        """
        This magic method is called when a new instance of the class (or subclass) is created.
        It dynamically adds a new method to the class for each field in `orderable_fk_fields`.
        """
        new_class = super().__new__(cls)

        # Check if the list_display attribute exists, and if it does, create a local copy of that list.
        list_display_exists = hasattr(cls, "list_display")
        new_list_display = []
        if list_display_exists and isinstance(cls.list_display, list):
            new_list_display = cls.list_display.copy()

        for field, sort_field in cls.orderable_fk_fields:
            updated_name = f"get_{field}"

            # For each item in orderable_fk_fields, create a function and associate it with admin_order_field. 
            setattr(new_class, updated_name, cls._create_orderable_field_method(field, sort_field))

            # Update the list_display variable to use our newly created functions
            if list_display_exists and field in cls.list_display:
                index = new_list_display.index(field)
                new_list_display[index] = updated_name
            elif list_display_exists:
                new_list_display.append(updated_name)

        # Replace the old list with the updated one
        if list_display_exists:
            cls.list_display = new_list_display

        return new_class

    @classmethod
    def _create_orderable_field_method(cls, field, sort_field):
        """
        This class method is a factory for creating dynamic methods that will be attached to the ModelAdmin subclass.
        It is used to customize how fk fields are ordered. 

        In essence, this function will more or less generate code that looks like this, 
        for a given tuple defined in orderable_fk_fields:
        
        ```
        def get_requested_domain(self, obj):
            return obj.requested_domain
        # Allows column order sorting
        get_requested_domain.admin_order_field = "requested_domain__name"
        # Sets column's header name
        get_requested_domain.short_description = "requested domain"  
        ```

        Or for fields with multiple order_fields:

        ```
        def get_submitter(self, obj):
            return obj.submitter
        # Allows column order sorting
        get_requested_domain.admin_order_field = ["submitter__first_name", "submitter__last_name"] 
        # Sets column's header 
        get_requested_domain.short_description = "submitter"  
        ```

        Parameters:
        cls: The class that this method is being called on. In the context of this mixin, it would be the ModelAdmin subclass.
        field: A string representing the name of the attribute that the dynamic method will fetch from the model instance.
        sort_field: A string or list of strings representing the field(s) to sort by (ex: "name" or "creator")

        Returns:
        method: The dynamically created method.

        The dynamically created method has the following attributes:
        __name__: A string representing the name of the method. This is set to "get_{field}".
        admin_order_field: A string or list of strings representing the field(s) that Django should sort by when the column is clicked in the admin interface.
        short_description: A string used as the column header in the admin interface. Will replace underscores with spaces.
        """
        def method(obj):
            """
            Method factory.
            """
            attr = getattr(obj, field)
            return attr

        # Set the function name. For instance, if the field is "domain",
        # then this will generate a function called "get_domain"
        method.__name__ = f"get_{field}"

        # Check if a list is passed in, or just a string.
        if isinstance(sort_field, list):
            sort_list = []
            for sort_field_item in sort_field:
                order_field_string = f"{field}__{sort_field_item}"
                sort_list.append(order_field_string)
            # If its a list, return an array of fields to sort on.
            # For instance, ["creator__first_name", "creator__last_name"]
            method.admin_order_field = sort_list
        else:
            # If its not a list, just return a string
            method.admin_order_field = f"{field}__{sort_field}"

        # Infer the column name in a similar manner to how Django does
        method.short_description = field.replace("_", " ")
        return method


class PermissionsLoginMixin(PermissionRequiredMixin):

    """Mixin that redirects to login page if not logged in, otherwise 403."""

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class DomainPermission(PermissionsLoginMixin):

    """Does the logged-in user have access to this domain?"""

    def has_permission(self):
        """Check if this user has access to this domain.

        The user is in self.request.user and the domain needs to be looked
        up from the domain's primary key in self.kwargs["pk"]
        """

        if not self.request.user.is_authenticated:
            return False

        if self.request.user.is_restricted():
            return False

        pk = self.kwargs["pk"]
        # If pk is none then something went very wrong...
        if pk is None:
            raise ValueError("Primary key is None")

        # test if domain in editable state
        if not self.in_editable_state(pk):
            return False

        if self.can_access_other_user_domains(pk):
            return True

        # user needs to have a role on the domain
        if not UserDomainRole.objects.filter(user=self.request.user, domain__id=pk).exists():
            return False

        # if we need to check more about the nature of role, do it here.
        return True

    def in_editable_state(self, pk):
        """Is the domain in an editable state"""

        requested_domain = None
        if Domain.objects.filter(id=pk).exists():
            requested_domain = Domain.objects.get(id=pk)

        # if domain is editable return true
        if requested_domain and requested_domain.is_editable():
            return True
        return False

    def can_access_other_user_domains(self, pk):
        """Checks to see if an authorized user (staff or superuser)
        can access a domain that they did not create or was invited to.
        """

        # Check if the user is permissioned...
        user_is_analyst_or_superuser = self.request.user.has_perm(
            "registrar.analyst_access_permission"
        ) or self.request.user.has_perm("registrar.full_access_permission")

        if not user_is_analyst_or_superuser:
            return False

        # Check if the user is attempting a valid edit action.
        # In other words, if the analyst/admin did not click
        # the 'Manage Domain' button in /admin,
        # then they cannot access this page.
        session = self.request.session
        can_do_action = (
            "analyst_action" in session
            and "analyst_action_location" in session
            and session["analyst_action_location"] == pk
        )

        if not can_do_action:
            return False

        # Analysts may manage domains, when they are in these statuses:
        valid_domain_statuses = [
            DomainApplication.ApplicationStatus.APPROVED,
            DomainApplication.ApplicationStatus.IN_REVIEW,
            DomainApplication.ApplicationStatus.REJECTED,
            DomainApplication.ApplicationStatus.ACTION_NEEDED,
            # Edge case - some domains do not have
            # a status or DomainInformation... aka a status of 'None'.
            # It is necessary to access those to correct errors.
            None,
        ]

        requested_domain = None
        if DomainInformation.objects.filter(id=pk).exists():
            requested_domain = DomainInformation.objects.get(id=pk)

        # if no domain information or application exist, the user
        # should be able to manage the domain; however, if domain information
        # and domain application exist, and application is not in valid status,
        # user should not be able to manage domain
        if (
            requested_domain
            and requested_domain.domain_application
            and requested_domain.domain_application.status not in valid_domain_statuses
        ):
            return False

        # Valid session keys exist,
        # the user is permissioned,
        # and it is in a valid status
        return True


class DomainApplicationPermission(PermissionsLoginMixin):

    """Does the logged-in user have access to this domain application?"""

    def has_permission(self):
        """Check if this user has access to this domain application.

        The user is in self.request.user and the domain needs to be looked
        up from the domain's primary key in self.kwargs["pk"]
        """
        if not self.request.user.is_authenticated:
            return False

        # user needs to be the creator of the application
        # this query is empty if there isn't a domain application with this
        # id and this user as creator
        if not DomainApplication.objects.filter(creator=self.request.user, id=self.kwargs["pk"]).exists():
            return False

        return True


class ApplicationWizardPermission(PermissionsLoginMixin):

    """Does the logged-in user have permission to start or edit an application?"""

    def has_permission(self):
        """Check if this user has permission to start or edit an application.

        The user is in self.request.user
        """

        # The user has an ineligible flag
        if self.request.user.is_restricted():
            return False

        return True


class DomainInvitationPermission(PermissionsLoginMixin):

    """Does the logged-in user have access to this domain invitation?

    A user has access to a domain invitation if they have a role on the
    associated domain.
    """

    def has_permission(self):
        """Check if this user has a role on the domain of this invitation."""
        if not self.request.user.is_authenticated:
            return False

        if not DomainInvitation.objects.filter(
            id=self.kwargs["pk"], domain__permissions__user=self.request.user
        ).exists():
            return False

        return True
