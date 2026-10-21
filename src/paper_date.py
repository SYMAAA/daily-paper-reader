"""Explicit publication-day recovery; normal runs retain their existing behavior."""
from datetime import datetime, timedelta, timezone


def publication_window(value):
    if len(value) != 10:
        raise ValueError("paper-date must be YYYY-MM-DD")
    start = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if start.strftime("%Y-%m-%d") != value:
        raise ValueError("paper-date must be YYYY-MM-DD")
    return start, start + timedelta(days=1)


def papers_on_date(papers, value):
    start, end = publication_window(value)
    result = []
    for paper in papers:
        try:
            dt = datetime.fromisoformat(str(paper.get("published") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
            if start <= dt.astimezone(timezone.utc) < end:
                result.append(paper)
        except (TypeError, ValueError):
            continue
    return result


def require_source_day(backend, value):
    """Fail before any writes if the shared source cannot confirm day coverage."""
    import json
    from urllib.parse import urlencode, quote
    from urllib.request import Request, urlopen
    start, end = publication_window(value)
    table = backend.get('papers_table') or 'arxiv_papers'
    query = urlencode([
        ('select', 'id'), ('published', 'gte.' + start.isoformat()),
        ('published', 'lt.' + end.isoformat()), ('limit', '1'),
    ])
    req = Request(backend['url'].rstrip('/') + '/rest/v1/' + quote(table, safe='') + '?' + query,
                  headers={'apikey': backend['anon_key'], 'Prefer': 'count=exact',
                           'Accept-Profile': backend.get('schema') or 'public'})
    with urlopen(req, timeout=60) as response:
        total = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
        json.load(response)
    if not total.isdigit() or int(total) == 0:
        raise ValueError(f'{value}: source has {total or "unknown"} papers; coverage unconfirmed, no archive written')
    print(f'[INFO] {value}: source papers={total}', flush=True)
    return int(total)
