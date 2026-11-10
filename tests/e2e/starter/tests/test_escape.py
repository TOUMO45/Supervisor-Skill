from csvmd import escape_cell


def test_escape_newline():
    assert escape_cell("a\nb") == "a b"
