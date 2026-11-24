import httpx
import pytest

from imports.fetch import MAX_BYTES, FetchError, check_url, fetch_feed

PUBLIC = "93.184.216.34"


def resolver_to(*addresses: str):
    return lambda host, port: list(addresses)


def client_answering(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://shop.example/feed.csv",
        "ftp://shop.example/feed.csv",
        "https://user:secret@shop.example/feed.csv",
        "https:///feed.csv",
    ],
)
def test_only_plain_https_urls(url):
    with pytest.raises(FetchError) as error:
        check_url(url, resolver_to(PUBLIC))
    assert not error.value.transient


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.0.70",
        "172.17.0.1",  # a Docker bridge
        "169.254.169.254",  # cloud metadata service
        "100.64.0.1",
        "::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
    ],
)
def test_private_addresses_are_refused(address):
    with pytest.raises(FetchError) as error:
        check_url("https://shop.example/feed.csv", resolver_to(address))
    assert not error.value.transient


def test_one_private_address_among_public_ones_is_enough_to_refuse():
    with pytest.raises(FetchError):
        check_url("https://shop.example/feed.csv", resolver_to(PUBLIC, "10.0.0.1"))


def test_dns_failure_is_temporary():
    def failing(host, port):
        raise OSError("temporary failure in name resolution")

    with pytest.raises(FetchError) as error:
        check_url("https://shop.example/feed.csv", failing)
    assert error.value.transient


def test_download():
    client = client_answering(
        lambda request: httpx.Response(200, content=b"a,b", headers={"content-type": "text/csv"})
    )

    download = fetch_feed("https://shop.example/f", client=client, resolver=resolver_to(PUBLIC))

    assert (download.content, download.content_type) == (b"a,b", "text/csv")


@pytest.mark.parametrize(
    "response, transient",
    [
        (httpx.Response(302, headers={"location": "http://10.0.0.1/"}), False),
        (httpx.Response(404), False),
        (httpx.Response(429), True),
        (httpx.Response(503), True),
        (httpx.Response(200, headers={"content-length": str(MAX_BYTES + 1)}), False),
        (httpx.Response(200, content=b"x" * (MAX_BYTES + 1)), False),
    ],
)
def test_bad_answers(response, transient):
    client = client_answering(lambda request: response)

    with pytest.raises(FetchError) as error:
        fetch_feed("https://shop.example/f", client=client, resolver=resolver_to(PUBLIC))
    assert error.value.transient is transient


def test_network_error_is_temporary():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(FetchError) as error:
        fetch_feed(
            "https://shop.example/f", client=client_answering(handler), resolver=resolver_to(PUBLIC)
        )
    assert error.value.transient
