import unittest


class Smoke(unittest.TestCase):
    def test_import(self):
        import shelfmark  # noqa: F401
