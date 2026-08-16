from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """Shared list-endpoint pagination — opt in per viewset via
    `pagination_class = StandardResultsPagination`, never globally (see the
    comment on REST_FRAMEWORK in settings.py for why). ?page=&page_size=,
    capped so a client can't request the whole table in one page."""

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'num_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })
