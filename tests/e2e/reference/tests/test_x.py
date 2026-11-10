import unittest
from csvmd import convert
class T(unittest.TestCase):
    def test(self): self.assertTrue(convert("a\n1\n"))
