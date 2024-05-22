from django.http import JsonResponse
from django.core.paginator import Paginator
from registrar.models import UserDomainRole, Domain

def get_domains_json(request):
    """Given the current request,
    get all domains that are associated with the UserDomainRole object"""

    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)

    user_domain_roles = UserDomainRole.objects.filter(user=request.user)
    domain_ids = user_domain_roles.values_list("domain_id", flat=True)

    objects = Domain.objects.filter(id__in=domain_ids)

    # Handle sorting
    sort_by = request.GET.get('sort_by', 'id')  # Default to 'id'
    order = request.GET.get('order', 'asc')  # Default to 'asc'

    if sort_by == 'state_display':
        # Fetch the objects and sort them in Python
        objects = list(objects)  # Evaluate queryset to a list
        objects.sort(key=lambda domain: domain.state_display(), reverse=(order == 'desc'))
    else:
        if order == 'desc':
            sort_by = f'-{sort_by}'
        objects = objects.order_by(sort_by)

    paginator = Paginator(objects, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Convert objects to JSON-serializable format
    domains = [
        {
            'id': domain.id,
            'name': domain.name,
            'expiration_date': domain.expiration_date,
            'state': domain.state,
            'state_display': domain.state_display(),
            'get_state_help_text': domain.get_state_help_text(),
            # Add other fields as necessary
        }
        for domain in page_obj.object_list
    ]

    return JsonResponse({
        'domains': domains,
        'page': page_obj.number,
        'num_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
    })