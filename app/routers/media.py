import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()


def _is_public_host(hostname: str | None) -> bool:
    if not hostname or hostname.lower() == "localhost":
        return False

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    has_public_ip = False
    for _, _, _, _, sockaddr in addrinfo:
        ip_text = sockaddr[0].split("%", 1)[0]
        try:
            ip_addr = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if (
            ip_addr.is_private
            or ip_addr.is_loopback
            or ip_addr.is_link_local
            or ip_addr.is_multicast
            or ip_addr.is_reserved
            or ip_addr.is_unspecified
        ):
            return False
        has_public_ip = True

    return has_public_ip


@router.get("/media/product-image")
def product_image_proxy(src: str = Query(..., min_length=1)) -> Response:
    target = src.strip()
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Некорректный URL изображения")
    if not _is_public_host(parsed.hostname):
        raise HTTPException(status_code=400, detail="Источник изображения запрещен")

    request = Request(
        target,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/*,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=8) as remote_response:
            payload = remote_response.read()
            content_type = remote_response.headers.get_content_type()
    except (HTTPError, URLError) as exc:
        raise HTTPException(
            status_code=404, detail="Не удалось загрузить изображение"
        ) from exc

    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=415, detail="Удаленный ресурс не является изображением"
        )

    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
