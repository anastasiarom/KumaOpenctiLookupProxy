from urllib.parse import urlparse
from typing import Iterable, Tuple, List

def normalize_search_value(items: Iterable) -> Tuple[List[str], List[str]]:
    search = []
    src = []

    for item in items:
        value = item.object.strip()

        search.append(value)
        src.append(value)

        if value.startswith(("http://", "https://")):
            hostname = urlparse(value).hostname
            if hostname:
                search.append(hostname)
    return search, src