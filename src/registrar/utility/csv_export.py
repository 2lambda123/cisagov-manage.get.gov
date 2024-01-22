import csv
import logging
from datetime import datetime
from registrar.models.domain import Domain
from registrar.models.domain_information import DomainInformation
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat, Coalesce


logger = logging.getLogger(__name__)


def write_header(writer, columns):
    """
    Receives params from the parent methods and outputs a CSV with a header row.
    Works with write_header as longas the same writer object is passed.
    """
    writer.writerow(columns)


def get_domain_infos(filter_condition, sort_fields):
    domain_infos = (
        DomainInformation.objects.select_related("domain", "authorizing_official")
        .filter(**filter_condition)
        .order_by(*sort_fields)
    )

    # Do a mass concat of the first and last name fields for authorizing_official.
    # The old operation was computationally heavy for some reason, so if we precompute
    # this here, it is vastly more efficient.
    domain_infos_cleaned = domain_infos.annotate(
        ao=Concat(
            Coalesce(F("authorizing_official__first_name"), Value("")),
            Value(" "),
            Coalesce(F("authorizing_official__last_name"), Value("")),
            output_field=CharField(),
        )
    )
    return domain_infos_cleaned


def parse_row(columns, domain_info: DomainInformation, skip_epp_call=True):
    """Given a set of columns, generate a new row from cleaned column data"""

    domain = domain_info.domain

    security_email = domain.security_contact_registry_id
    if security_email is None:
        cached_sec_email = domain.get_security_email(skip_epp_call)
        security_email = cached_sec_email if cached_sec_email is not None else " "

    invalid_emails = {"registrar@dotgov.gov", "dotgov@cisa.dhs.gov"}
    # These are default emails that should not be displayed in the csv report
    if security_email.lower() in invalid_emails:
        security_email = "(blank)"

    if domain_info.federal_type:
        domain_type = f"{domain_info.get_organization_type_display()} - {domain_info.get_federal_type_display()}"
    else:
        domain_type = domain_info.get_organization_type_display()

    # create a dictionary of fields which can be included in output
    FIELDS = {
        "Domain name": domain.name,
        "Domain type": domain_type,
        "Agency": domain_info.federal_agency,
        "Organization name": domain_info.organization_name,
        "City": domain_info.city,
        "State": domain_info.state_territory,
        "AO": domain_info.ao,
        "AO email": domain_info.authorizing_official.email if domain_info.authorizing_official else " ",
        "Security contact email": security_email,
        "Status": domain.get_state_display(),
        "Expiration date": domain.expiration_date,
        "Created at": domain.created_at,
        "First ready": domain.first_ready,
        "Deleted": domain.deleted,
    }

    row = [FIELDS.get(column, "") for column in columns]
    return row


def write_body(
    writer,
    columns,
    sort_fields,
    filter_condition,
):
    """
    Receives params from the parent methods and outputs a CSV with fltered and sorted domains.
    Works with write_header as longas the same writer object is passed.
    """

    # Get the domainInfos
    all_domain_infos = get_domain_infos(filter_condition, sort_fields)

    # Reduce the memory overhead when performing the write operation
    a1_start_time = time.time()
    paginator = Paginator(all_domain_infos, 1000)
    for page_num in paginator.page_range:
        page = paginator.page(page_num)
        rows = []
        for domain_info in page.object_list:
            row = parse_row(columns, domain_info)
            rows.append(row)

        writer.writerows(rows)


def export_data_type_to_csv(csv_file):
    """All domains report with extra columns"""

    writer = csv.writer(csv_file)
    # define columns to include in export
    columns = [
        "Domain name",
        "Domain type",
        "Agency",
        "Organization name",
        "City",
        "State",
        "AO",
        "AO email",
        "Security contact email",
        "Status",
        "Expiration date",
    ]
    # Coalesce is used to replace federal_type of None with ZZZZZ
    sort_fields = [
        "organization_type",
        Coalesce("federal_type", Value("ZZZZZ")),
        "federal_agency",
        "domain__name",
    ]
    filter_condition = {
        "domain__state__in": [
            Domain.State.READY,
            Domain.State.DNS_NEEDED,
            Domain.State.ON_HOLD,
        ],
    }
    write_header(writer, columns)
    write_body(writer, columns, sort_fields, filter_condition)


def export_data_full_to_csv(csv_file):
    """All domains report"""

    writer = csv.writer(csv_file)
    # define columns to include in export
    columns = [
        "Domain name",
        "Domain type",
        "Agency",
        "Organization name",
        "City",
        "State",
        "Security contact email",
    ]
    # Coalesce is used to replace federal_type of None with ZZZZZ
    sort_fields = [
        "organization_type",
        Coalesce("federal_type", Value("ZZZZZ")),
        "federal_agency",
        "domain__name",
    ]
    filter_condition = {
        "domain__state__in": [
            Domain.State.READY,
            Domain.State.DNS_NEEDED,
            Domain.State.ON_HOLD,
        ],
    }
    write_header(writer, columns)
    write_body(writer, columns, sort_fields, filter_condition)


def export_data_federal_to_csv(csv_file):
    """Federal domains report"""

    writer = csv.writer(csv_file)
    # define columns to include in export
    columns = [
        "Domain name",
        "Domain type",
        "Agency",
        "Organization name",
        "City",
        "State",
        "Security contact email",
    ]
    # Coalesce is used to replace federal_type of None with ZZZZZ
    sort_fields = [
        "organization_type",
        Coalesce("federal_type", Value("ZZZZZ")),
        "federal_agency",
        "domain__name",
    ]
    filter_condition = {
        "organization_type__icontains": "federal",
        "domain__state__in": [
            Domain.State.READY,
            Domain.State.DNS_NEEDED,
            Domain.State.ON_HOLD,
        ],
    }
    write_header(writer, columns)
    write_body(writer, columns, sort_fields, filter_condition)


def get_default_start_date():
    # Default to a date that's prior to our first deployment
    return timezone.make_aware(datetime(2023, 11, 1))


def get_default_end_date():
    # Default to now()
    return timezone.now()


def export_data_growth_to_csv(csv_file, start_date, end_date):
    """
    Growth report:
    Receive start and end dates from the view, parse them.
    Request from write_body READY domains that are created between
    the start and end dates, as well as DELETED domains that are deleted between
    the start and end dates. Specify sort params for both lists.
    """

    start_date_formatted = (
        timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d")) if start_date else get_default_start_date()
    )

    end_date_formatted = (
        timezone.make_aware(datetime.strptime(end_date, "%Y-%m-%d")) if end_date else get_default_end_date()
    )

    writer = csv.writer(csv_file)

    # define columns to include in export
    columns = [
        "Domain name",
        "Domain type",
        "Agency",
        "Organization name",
        "City",
        "State",
        "Status",
        "Expiration date",
        "Created at",
        "First ready",
        "Deleted",
    ]
    sort_fields = [
        "domain__first_ready",
        "domain__name",
    ]
    filter_condition = {
        "domain__state__in": [Domain.State.READY],
        "domain__first_ready__lte": end_date_formatted,
        "domain__first_ready__gte": start_date_formatted,
    }

    # We also want domains deleted between sar and end dates, sorted
    sort_fields_for_deleted_domains = [
        "domain__deleted",
        "domain__name",
    ]
    filter_condition_for_deleted_domains = {
        "domain__state__in": [Domain.State.DELETED],
        "domain__deleted__lte": end_date_formatted,
        "domain__deleted__gte": start_date_formatted,
    }

    write_header(writer, columns)
    write_body(writer, columns, sort_fields, filter_condition)
    write_body(writer, columns, sort_fields_for_deleted_domains, filter_condition_for_deleted_domains)
