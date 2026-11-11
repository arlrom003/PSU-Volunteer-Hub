"""Shared query-string preserving pagination for server-rendered lists."""
from flask import request, url_for
from types import SimpleNamespace
from urllib.parse import urlencode


def page_number(parameter='page'):
    return max(1, request.args.get(parameter, 1, type=int) or 1)


def paginate(query, per_page=25, parameter='page'):
    result = query.paginate(page=page_number(parameter), per_page=per_page, error_out=False)
    if result.page > max(1, result.pages):
        result = query.paginate(page=max(1, result.pages), per_page=per_page, error_out=False)
    return result


def page_url(number, parameter='page', anchor=None):
    values = request.args.to_dict(flat=False)
    values.pop('show', None)
    values[parameter] = number
    path, _, fragment = url_for(request.endpoint, **(request.view_args or {}), _anchor=anchor).partition('#')
    return path + '?' + urlencode(values, doseq=True) + ('#' + fragment if fragment else '')


def report_page(scope, total, per_page=25):
    from app.reports import build_events_report
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page_number(), pages)
    rows, _ = build_events_report(**scope, limit=per_page, offset=(page - 1) * per_page,
                                  include_summary=False)
    return SimpleNamespace(items=rows, total=total, pages=pages, page=page,
                           has_prev=page > 1, has_next=page < pages,
                           prev_num=page - 1, next_num=page + 1)
