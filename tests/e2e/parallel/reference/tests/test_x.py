import unittest
from textkit import slugify
class T(unittest.TestCase):
    def test(self): self.assertEqual(slugify("A B"), "a-b")
