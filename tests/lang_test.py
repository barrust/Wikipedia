# -*- coding: utf-8 -*-
import unittest
from collections import defaultdict

from wikipedia import wikipedia
class language(object):
  ''' _wiki_request override '''
  calls = defaultdict(int)

  @classmethod
  def __call__(cls, params):
    cls.calls[params.__str__()] += 1
    return True

wikipedia.language = language
wikipedia.WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] = (1,28,)
wikipedia.WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS'] = ['TextExtracts', 'GeoData']



class TestLang(unittest.TestCase):
  """Test the ability for wikipedia to change the language of the API being accessed."""

  def test_lang(self):
    ''' ensure the url gets updated correctly '''
    wikipedia.set_lang("fr")
    self.assertEqual(wikipedia.WIKIPEDIA_GLOBALS['API_URL'], 'http://fr.wikipedia.org/w/api.php')
