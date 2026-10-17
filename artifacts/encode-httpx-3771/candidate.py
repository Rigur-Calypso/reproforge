from httpx._utils import unquote


def test_unquote_empty_string():
    assert unquote("") == ""