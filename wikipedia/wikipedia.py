from __future__ import unicode_literals

import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from decimal import Decimal

from .exceptions import (
    PageError, DisambiguationError, RedirectError, HTTPTimeoutError,
    WikipediaException, WikipediaAPIURLError, WikipediaAPILanguageError,
    WikipediaAPIVersionError, WikipediaExtensionError, ODD_ERROR_MESSAGE)
from .util import cache, stdout_encode, debug, _cmp_major_minor

def get_version():
    ''' Return Version Number'''
    return "1.4.5"

WIKIPEDIA_GLOBALS = {
    'API_URL': 'http://en.wikipedia.org/w/api.php',
    'API_VERSION': None,
    'API_VERSION_MAJOR_MINOR': None,
    'INSTALLED_EXTENSIONS': None,
    'LANGUAGE_PREFIX': 'en',
    'RATE_LIMIT': False,
    'RATE_LIMIT_MIN_WAIT': None,
    'RATE_LIMIT_LAST_CALL': None,
    'USER_AGENT': 'python-mediawiki/{0} (https://github.com/barrust/Wikipedia/) BOT'.format(get_version()),
    'SESSION': None,
    'TIMEOUT': None
}

def set_api_url(api_url, prefix):
    '''
    Change the mediawiki site from which pages should be retrieved.
    '''
    global WIKIPEDIA_GLOBALS
    WIKIPEDIA_GLOBALS['API_URL'] = api_url
    WIKIPEDIA_GLOBALS['LANGUAGE_PREFIX'] = prefix
    clear_cache()
    try:
        langs = languages()
    except Exception as e:
        raise WikipediaAPIURLError(api_url)

    _get_site_info()

def get_api_version():
    '''
    Return the API version of the Mediawiki site
    '''
    global WIKIPEDIA_GLOBALS
    return WIKIPEDIA_GLOBALS['API_VERSION']

def get_installed_extensions():
    '''
    Return the installed extensions of the Mediawiki site
    '''
    global WIKIPEDIA_GLOBALS
    return WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']

def set_lang(prefix):
    '''
    Change the language of the API being requested.
    Set `prefix` to one of the two letter prefixes found on the `list of all Wikipedias <http://meta.wikimedia.org/wiki/List_of_Wikipedias>`_.
    After setting the language, the cache for ``search``, ``suggest``, and ``summary`` will be cleared.

    .. note:: Make sure you search for page titles in the language that you have set.
    '''
    global WIKIPEDIA_GLOBALS
    old_prefix = WIKIPEDIA_GLOBALS['LANGUAGE_PREFIX']
    tmp_url = WIKIPEDIA_GLOBALS['API_URL'].replace('/{0}.'.format(old_prefix), "/{0}.".format(prefix.lower()))

    if WIKIPEDIA_GLOBALS['API_URL'] == tmp_url:
        raise WikipediaAPILanguageError(WIKIPEDIA_GLOBALS['API_URL'], old_prefix, prefix.lower())

    try:
        langs = languages()
    except Exception as e:
        raise WikipediaAPIURLError(tmp_url)

    WIKIPEDIA_GLOBALS['LANGUAGE_PREFIX'] = prefix.lower()
    WIKIPEDIA_GLOBALS['API_URL'] = tmp_url
    clear_cache()

def clear_cache():
    ''' Clear the cached results as necessary '''
    for cached_func in (search, suggest, summary, categorymembers, geosearch, opensearch):
        cached_func.clear_cache()

def set_user_agent(user_agent_string):
    '''
    Set the User-Agent string to be used for all requests.

    Arguments:

    * user_agent_string - (string) a string specifying the User-Agent header
    '''
    global WIKIPEDIA_GLOBALS

    WIKIPEDIA_GLOBALS['USER_AGENT'] = user_agent_string
    reset_session()

def get_user_agent():
    ''' See User Agent string '''
    global WIKIPEDIA_GLOBALS
    return WIKIPEDIA_GLOBALS['USER_AGENT']

def set_timeout(timeout):
    '''
        Set the HTTP timeout variable
        .. note:: Use None for no timeout
    '''
    global WIKIPEDIA_GLOBALS
    WIKIPEDIA_GLOBALS['TIMEOUT'] = timeout

def reset_session():
    ''' Reset HTTP session '''
    global WIKIPEDIA_GLOBALS
    headers = {
        'User-Agent': WIKIPEDIA_GLOBALS['USER_AGENT']
    }
    WIKIPEDIA_GLOBALS['SESSION'] = requests.Session()
    WIKIPEDIA_GLOBALS['SESSION'].headers.update(headers)

def set_rate_limiting(rate_limit, min_wait=timedelta(milliseconds=50)):
    '''
    Enable or disable rate limiting on requests to the Mediawiki servers.
    If rate limiting is not enabled, under some circumstances (depending on
    load on Wikipedia, the number of requests you and other `wikipedia` users
    are making, and other factors), Wikipedia may return an HTTP timeout error.

    Enabling rate limiting generally prevents that issue, but please note that
    HTTPTimeoutError still might be raised.

    Arguments:

    * rate_limit - (Boolean) whether to enable rate limiting or not

    Keyword arguments:

    * min_wait - if rate limiting is enabled, `min_wait` is a timedelta describing the minimum time to wait before requests.
                 Defaults to timedelta(milliseconds=50)
    '''
    global WIKIPEDIA_GLOBALS

    WIKIPEDIA_GLOBALS['RATE_LIMIT'] = rate_limit
    if not rate_limit:
        WIKIPEDIA_GLOBALS['RATE_LIMIT_MIN_WAIT'] = None
    else:
        WIKIPEDIA_GLOBALS['RATE_LIMIT_MIN_WAIT'] = min_wait

    WIKIPEDIA_GLOBALS['RATE_LIMIT_LAST_CALL'] = None


@cache
def search(query, results=10, suggestion=False):
    '''
    Do a Wikipedia search for `query`.

    Keyword arguments:

    * results - the maxmimum number of results returned
    * suggestion - if True, return results and suggestion (if any) in a tuple

    .. note:: MediaWiki version >= 1.16
    '''

    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 16]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.16", 'search')


    if query is None or query.strip() == '':
        raise ValueError("Query must be specified")
    search_params = {
        'list': 'search',
        'srprop': '',
        'srlimit': results,
        'srsearch': query
    }
    if suggestion:
        search_params['srinfo'] = 'suggestion'

    raw_results = _wiki_request(search_params)

    if 'error' in raw_results:
        if raw_results['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
            raise HTTPTimeoutError(query)
        else:
            raise WikipediaException(raw_results['error']['info'])

    search_results = (d['title'] for d in raw_results['query']['search'])

    if suggestion:
        if raw_results['query'].get('searchinfo'):
            return list(search_results), raw_results['query']['searchinfo']['suggestion']
        else:
            return list(search_results), None

    return list(search_results)

@cache
def categorymembers(category, results=10, subcategories=True):
    '''
    Do a Wikipedia search for pages, and optionally sub-categories, that belong to a `category`.

    Keyword arguments:

    * results - the maxmimum number of results returned
    * subcategories - if True, return pages and sub-categories (if any) in a tuple

    .. note:: MediaWiki version >= 1.17
    '''

    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 17]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.17", 'categorymembers')


    if category is None or category.strip() == '':
        raise ValueError("Category must be specified")

    search_params = {
        'list': 'categorymembers',
        'cmprop': 'ids|title|type',
        'cmtype': ('page|subcat' if subcategories else 'page'), # could also include files
        'cmlimit': results,
        'cmtitle': 'Category:' + category
    }

    raw_results = _wiki_request(search_params)

    if 'error' in raw_results:
        if raw_results['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
            raise HTTPTimeoutError(query)
        else:
            raise WikipediaException(raw_results['error']['info'])

    pages = list()
    subcats = list()
    for d in raw_results['query']['categorymembers']:
        if d['type'] == 'page':
            pages.append(d['title'])
        elif d['type'] == 'subcat':
            tmp = d['title']
            if tmp.startswith('Category:'):
                tmp = tmp[9:]
            subcats.append(tmp)
    if subcategories:
        return pages, subcats
    else:
        return pages

def categorytree(category, depth=5):
    '''
    Build a category tree for either a single category or a list of categories

    Keyword arguments:

    * depth - the maxmimum number of levels returned. < 0 for all levels

    .. note:: Set depth to 0 to get the full tree

    .. note:: Recommended to set rate limit to True

    .. warning:: Very long running! Requires many calls to categorymembers; recommend setting rate limit before running.
    '''

    def __cat_tree_rec(cat, depth, tree, level, categories, links):
        ''' recursive function to build out the tree '''
        tree[cat] = dict()
        tree[cat]['depth'] = level
        tree[cat]['sub-categories'] = dict()
        tree[cat]['links'] = list()
        tree[cat]['parent-categories'] = list()

        if cat not in categories:
            while True:
                try:
                    categories[cat] = page('Category:{0}'.format(cat))
                    categories[cat].categories
                    links[cat] = categorymembers(cat, 500, True)
                    break
                except PageError as e:
                    raise PageError(cat)
                except Exception as e:
                    time.sleep(1)

        for p in categories[cat].categories:
             tree[cat]['parent-categories'].append(p)

        for link in links[cat][0]:
            tree[cat]['links'].append(link)

        if level >= depth > 0:
            for c in links[cat][1]:
                tree[cat]['sub-categories'][c] = None
        else:
            for c in links[cat][1]:
                __cat_tree_rec(c, depth, tree[cat]['sub-categories'], level + 1, categories, links)
        return
    # end __cat_tree_rec

    # make it simple to use both a list or a single category term
    if type(category) is not list:
        cats = [category]
    else:
        cats = category

    results = dict()
    categories = dict()
    links = dict()
    for cat in cats:
        __cat_tree_rec(cat, depth, results, 0, categories, links)
    return results


@cache
def geosearch(latitude, longitude, title=None, results=10, radius=1000):
    '''
    Do a wikipedia geo search for `latitude` and `longitude`
    using HTTP API described in http://www.mediawiki.org/wiki/Extension:GeoData

    Arguments:

    * latitude (float or decimal.Decimal)
    * longitude (float or decimal.Decimal)

    Keyword arguments:

    * title - The title of an article to search for
    * results - the maximum number of results returned
    * radius - Search radius in meters. The value must be between 10 and 10000

    .. note:: Requires GeoData extension
    '''
    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if 'GeoData' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
        raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'GeoData', 'geosearch')

    if latitude is None or (type(latitude) != Decimal and latitude.strip() == ''):
        raise ValueError("Latitude must be specified")
    if longitude is None or (type(longitude) != Decimal and longitude.strip() == ''):
        raise ValueError("Longitude must be specified")

    search_params = {
        'list': 'geosearch',
        'gsradius': radius,
        'gscoord': '{0}|{1}'.format(latitude, longitude),
        'gslimit': results
    }
    if title:
        search_params['titles'] = title

    raw_results = _wiki_request(search_params)

    if 'error' in raw_results:
        if raw_results['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
            raise HTTPTimeoutError('{0}|{1}'.format(latitude, longitude))
        else:
            raise WikipediaException(raw_results['error']['info'])

    search_pages = raw_results['query'].get('pages')
    if search_pages:
        search_results = (v['title'] for k, v in search_pages.items() if k != '-1')
    else:
        search_results = (d['title'] for d in raw_results['query']['geosearch'])

    return list(search_results)

@cache
def opensearch(query, results=10, redirect=False):
    '''
    Execute a Wikipedia opensearch request, similar to search box suggestions and conforming to the OpenSearch specification.

    Keyword arguments:

    * results - the maxmimum number of results returned (limited to 100 total by the API)
    * redirect - if True, return the redirect itself otherwise return the target page which may return fewer than limit results.

    Returns:

    * List of tuples: Title, Summary, and URL

    .. note:: MediaWiki Version >= 1.25 OR OpenSearch extension
    '''
    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 25]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.25", 'opensearch')
    elif 'OpenSearch' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
        raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'OpenSearch', 'opensearch')

    if query is None or query.strip() == '':
        raise ValueError("Query must be specified")

    query_params = {
        'action': 'opensearch',
        'search': query,
        'limit': (100 if results > 100 else results),
        'redirects': ('resolve' if redirect is True else 'return'),
        'warningsaserror': True,
        'namespace': ''
    }

    raw_results = _wiki_request(query_params)

    if 'error' in raw_results:
        raise WikipediaException(raw_results['error']['info'])

    res = list()
    for i in range(0, len(raw_results[1])):
        res.append((raw_results[1][i], raw_results[2][i], raw_results[3][i],))

    return res

@cache
def prefexsearch(query, results=10):
    '''
    Request a prefex based search exactly like the Wikipedia search box results.

    Keyword arguments:

    * results - the maxmimum number of results returned (limited to 100 total by the API)

    .. note:: MediaWiki API Version >= 1.23
    '''
    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 23]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.23", 'prefixsearch')

    if query is None or query.strip() == '':
        raise ValueError("Query must be specified")

    query_params = {
        'action': 'query',
        'list': 'prefixsearch',
        'pssearch': query,
        'pslimit': (100 if results > 100 else results),
        'psnamespace': 0,
        'psoffset': 0 # this could be added as a parameter to allow for skipping to later in the list
    }

    raw_results = _wiki_request(query_params)

    if 'error' in raw_results:
        raise WikipediaException(raw_results['error']['info'])

    res = list()
    for d in raw_results['query']['prefixsearch']:
        res.append(d['title'])

    return res

@cache
def suggest(query):
    '''
    Get a Wikipedia search suggestion for `query`.
    Returns a string or None if no suggestion was found.

    .. note:: MediaWiki API Version >= 1.16
    '''

    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 16]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.16", 'suggest')

    if query is None or query.strip() == '':
        raise ValueError("Query must be specified")

    search_params = {
        'list': 'search',
        'srinfo': 'suggestion',
        'srprop': '',
        'srsearch': query
    }

    raw_result = _wiki_request(search_params)

    if raw_result['query'].get('searchinfo'):
        return raw_result['query']['searchinfo']['suggestion']

    return None


def random(pages=1):
    '''
    Get a list of random Wikipedia article titles.

    .. note:: Random only gets articles from namespace 0, meaning no Category, User talk, or other meta-Wikipedia pages.

    Keyword arguments:

    * pages - the number of random pages returned (max of 10)

    .. note:: MediaWiki API Version >= 1.12
    '''
    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 12]):
        raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.12", 'random')

    #http://en.wikipedia.org/w/api.php?action=query&list=random&rnlimit=5000&format=jsonfm
    if pages is None or pages < 1:
        raise ValueError('Number of pages must be greater than 0')
    query_params = {
        'list': 'random',
        'rnnamespace': 0,
        'rnlimit': pages,
    }

    request = _wiki_request(query_params)
    titles = [page['title'] for page in request['query']['random']]

    if len(titles) == 1:
        return titles[0]

    return titles


@cache
def summary(title, sentences=0, chars=0, auto_suggest=True, redirect=True):
    '''
    Plain text summary of the page.

    .. note:: This is a convenience wrapper - auto_suggest and redirect are enabled by default

    Keyword arguments:

    * sentences - if set, return the first `sentences` sentences (can be no greater than 10).
    * chars - if set, return only the first `chars` characters (actual text returned may be slightly longer).
    * auto_suggest - let Wikipedia find a valid page title for the query
    * redirect - allow redirection without raising RedirectError

    .. note:: Requires TextExtracts extension to be installed on MediaWiki server
    '''
    global WIKIPEDIA_GLOBALS
    if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
        _get_site_info()

    if 'TextExtracts' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
        raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'TextExtracts', 'summary()')

    if title is None or title.strip() == '':
        raise ValueError('Summary title must be specified.')

    # use auto_suggest and redirect to get the correct article
    # also, use page's error checking to raise DisambiguationError if necessary
    page_info = page(title, auto_suggest=auto_suggest, redirect=redirect)

    return page_info.get_summary(sentences, chars)


def page(title=None, pageid=None, auto_suggest=True, redirect=True, preload=False):
    '''
    Get a WikipediaPage object for the page with title `title` or the pageid
    `pageid` (mutually exclusive).

    Keyword arguments:

    * title - the title of the page to load
    * pageid - the numeric pageid of the page to load
    * auto_suggest - let Wikipedia find a valid page title for the query
    * redirect - allow redirection without raising RedirectError
    * preload - load content, summary, images, references, and links during initialization

    .. note:: Any property that the MediaWiki site does not support will be set to None if preload is used and no exception will be thrown
    '''

    if title is not None and title.strip() != '':
        if auto_suggest:
            results, suggestion = search(title, results=1, suggestion=True)
            try:
                title = suggestion or results[0]
                # title = results[0] or suggestion #should these be flipped?
            except IndexError:
                # if there is no suggestion or search results, the page doesn't exist
                raise PageError(title)
        return WikipediaPage(title, redirect=redirect, preload=preload)
    elif pageid is not None:
        return WikipediaPage(pageid=pageid, preload=preload)
    else:
        raise ValueError("Either a title or a pageid must be specified")



class WikipediaPage(object):
    '''
    Contains data from a Wikipedia page.
    Uses property methods to filter data from the raw HTML.
    '''

    def __init__(self, title=None, pageid=None, redirect=True, preload=False, original_title=''):
        global WIKIPEDIA_GLOBALS
        if WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] is None:
            _get_site_info()

        if title is not None:
            self.title = title
            self.original_title = original_title or title
        elif pageid is not None:
            self.pageid = pageid
        else:
            raise ValueError("Either a title or a pageid must be specified")

        self.__load(redirect=redirect, preload=preload)

        if preload:
            for prop in ('content', 'summary', 'images', 'references', 'links', 'sections', 'redirects', 'coordinates', 'backlinks', 'categories'):
                try:
                    getattr(self, prop)
                except WikipediaAPIVersionError:
                    pass
                except WikipediaExtensionError:
                    pass

    def __repr__(self):
        return stdout_encode(u'<WikipediaPage \'{0}\'>'.format(self.title))

    def __eq__(self, other):
        try:
            return (
                self.pageid == other.pageid
                and self.title == other.title
                and self.url == other.url
            )
        except AttributeError as ex:
            return False

    def __load(self, redirect=True, preload=False):
        '''
        Load basic information from Wikipedia.
        Confirm that page exists and is not a disambiguation/redirect.

        Does not need to be called manually, should be called automatically during __init__.
        '''
        query_params = {
            'prop': 'info|pageprops',
            'inprop': 'url',
            'ppprop': 'disambiguation',
            'redirects': '',
        }
        query_params.update(self.__title_query_param)

        request = _wiki_request(query_params)

        query = request['query']
        pageid = list(query['pages'].keys())[0]
        page = query['pages'][pageid]

        # missing is present if the page is missing
        if 'missing' in page:
            if hasattr(self, 'title'):
                raise PageError(self.title)
            else:
                raise PageError(pageid=self.pageid)

        # same thing for redirect, except it shows up in query instead of page for
        # whatever silly reason
        elif 'redirects' in query:
            if redirect:
                redirects = query['redirects'][0]

                if 'normalized' in query:
                    normalized = query['normalized'][0]
                    assert normalized['from'] == self.title, ODD_ERROR_MESSAGE

                    from_title = normalized['to']

                else:
                    if not getattr(self, 'title', None):
                        self.title = redirects['from']
                        delattr(self, 'pageid')
                    from_title = self.title

                assert redirects['from'] == from_title, ODD_ERROR_MESSAGE

                # change the title and reload the whole object
                self.__init__(redirects['to'], redirect=redirect, preload=preload)

            else:
                raise RedirectError(getattr(self, 'title', page['title']))

        # since we only asked for disambiguation in ppprop,
        # if a pageprop is returned,
        # then the page must be a disambiguation page
        elif 'pageprops' in page:
            query_params = {
                'prop': 'revisions',
                'rvprop': 'content',
                'rvparse': '',
                'rvlimit': 1
            }
            query_params.update(self.__title_query_param)
            request = _wiki_request(query_params)
            html = request['query']['pages'][pageid]['revisions'][0]['*']

            lis = BeautifulSoup(html, 'html.parser').find_all('li')
            filtered_lis = [li for li in lis if not 'tocsection' in ''.join(li.get('class', list()))]
            may_refer_to = [li.a.get_text() for li in filtered_lis if li.a]
            disambiguation = list()
            for lis_item in filtered_lis:
                one_disambiguation = dict()
                item = lis_item.find_all("a")[0]
                if item:
                    one_disambiguation["title"] = item["title"]
                    one_disambiguation["description"] = lis_item.text
                    disambiguation.append(one_disambiguation)
            raise DisambiguationError(getattr(self, 'title', page['title']), may_refer_to, disambiguation)

        else:
            self.pageid = pageid
            self.title = page['title']
            self.url = page['fullurl']

    def __continued_query(self, query_params):
        '''
        Based on https://www.mediawiki.org/wiki/API:Query#Continuing_queries
        '''
        query_params.update(self.__title_query_param)

        last_continue = dict()
        prop = query_params.get('prop')

        while True:
            params = query_params.copy()
            params.update(last_continue)

            request = _wiki_request(params)

            if 'query' not in request:
                break

            pages = request['query']['pages']
            if 'generator' in query_params:
                for datum in pages.values():    # in python 3.3+: "yield from pages.values()"
                    yield datum
            else:
                for datum in pages[self.pageid].get(prop, list()):
                    yield datum

            if 'continue' not in request:
                break

            last_continue = request['continue']

    @property
    def __title_query_param(self):
        ''' util function to determine which parameter method to use '''
        if getattr(self, 'title', None) is not None:
            return {'titles': self.title}
        else:
            return {'pageids': self.pageid}

    def html(self):
        '''
        Get full page HTML.

        .. warning:: This can get pretty slow on long pages.

        .. note:: MediaWiki version >= 1.17
        '''

        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_html', False):
            self._html = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 17]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.17", 'html')

            query_params = {
                'prop': 'revisions',
                'rvprop': 'content',
                'rvlimit': 1,
                'rvparse': '',
                'titles': self.title
            }

            request = _wiki_request(query_params)
            self._html = request['query']['pages'][self.pageid]['revisions'][0]['*']

        return self._html

    @property
    def content(self):
        '''
        Plain text content of the page, excluding images, tables, and other data.

        .. note:: Requires TextExtracts extension to be installed on MediaWiki server >= 1.11
        '''

        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_content', False):
            self._content = None
            self._revision_id = None
            self._parent_id = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 11]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.11", 'content')
            if 'TextExtracts' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
                raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'TextExtracts', 'content')

            query_params = {
                'prop': 'extracts|revisions',
                'explaintext': '',
                'rvprop': 'ids'
            }
            query_params.update(self.__title_query_param)
            request = _wiki_request(query_params)
            self._content     = request['query']['pages'][self.pageid]['extract']
            self._revision_id = request['query']['pages'][self.pageid]['revisions'][0]['revid']
            self._parent_id   = request['query']['pages'][self.pageid]['revisions'][0]['parentid']

        return self._content

    @property
    def revision_id(self):
        '''
        Revision ID of the page.

        The revision ID is a number that uniquely identifies the current
        version of the page. It can be used to create the permalink or for
        other direct API calls. See `Help:Page history
        <http://en.wikipedia.org/wiki/Wikipedia:Revision>`_ for more
        information.

        .. note:: Requires TextExtracts extension to be installed on MediaWiki server >= 1.11
        '''
        if not getattr(self, '_revid', False):
            # fetch the content (side effect is loading the revid)
            self.content

        return self._revision_id

    @property
    def parent_id(self):
        '''
        Revision ID of the parent version of the current revision of this
        page. See ``revision_id`` for more information.

        .. note:: Requires TextExtracts extension to be installed on MediaWiki server >= 1.11
        '''
        if not getattr(self, '_parentid', False):
            # fetch the content (side effect is loading the parentid)
            self.content

        return self._parent_id

    @property
    def summary(self):
        '''
        Plain text summary of the page.

        .. note:: This is the same as calling page.get_summary()

        .. note:: Requires TextExtracts extension to be installed on MediaWiki server
        '''
        if not getattr(self, '_summary', False):
            self._summary = None # if it throws an exception that is caught, it will be set
            self._summary = self.get_summary()

        return self._summary

    def get_summary(self, sentences=0, chars=0):
        '''
        Plain text summary of the page.

        Keyword arguments:

        * sentences - if set, return the first `sentences` sentences (can be no greater than 10).
        * chars - if set, return only the first `chars` characters (actual text returned may be slightly longer).

        .. note:: Requires TextExtracts extension to be installed on MediaWiki server
        '''
        global WIKIPEDIA_GLOBALS
        if 'TextExtracts' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
            raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'TextExtracts', 'get_summary()')

        query_params = {
            'prop': 'extracts',
            'explaintext': '',
            'titles': self.title
        }

        if sentences:
            query_params['exsentences'] = (10 if sentences > 10 else sentences)
        elif chars:
            query_params['exchars'] = (1 if chars < 1 else chars)
        else:
            query_params['exintro'] = ''

        request = _wiki_request(query_params)
        summary = request['query']['pages'][self.pageid]['extract']
        return summary

    @property
    def images(self):
        '''
        List of URLs of images on the page.
        '''
        if not getattr(self, '_images', False):
            self._images = list()
            for page in self.__continued_query({'generator': 'images', 'gimlimit': 'max', 'prop': 'imageinfo', 'iiprop': 'url'}):
                if 'imageinfo' in page:
                    self._images.append(page['imageinfo'][0]['url'])

        return self._images

    @property
    def coordinates(self):
        '''
        Tuple of Decimals in the form of (lat, lon) or None

        .. note:: Requires GeoData extension
        '''
        global WIKIPEDIA_GLOBALS

        if not getattr(self, '_coordinates', False):
            self._coordinates = None

            if 'GeoData' not in WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS']:
                raise WikipediaExtensionError(WIKIPEDIA_GLOBALS['API_URL'], 'GeoData', 'coordinates')

            # add geodata check here
            request = _wiki_request({'prop': 'coordinates', 'colimit': 'max', 'titles': self.title})

            if 'query' in request and 'coordinates' in request['query']['pages'][self.pageid]:
                coordinates = request['query']['pages'][self.pageid]['coordinates']
                self._coordinates = (Decimal(coordinates[0]['lat']), Decimal(coordinates[0]['lon']))

        return self._coordinates

    @property
    def references(self):
        '''
        List of URLs of external links on a page.
        May include external links within page that aren't technically cited anywhere.

        .. note:: MediaWiki version >= 1.13
        '''

        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_references', False):
            self._references = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 13]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.13", 'references')

            self._references = list()
            for link in self.__continued_query({'prop': 'extlinks', 'ellimit': 'max'}):
                url = link['*'] if link['*'].startswith('http') else 'http:' + link['*']
                self._references.append(url)

        return self._references

    @property
    def links(self):
        '''
        List of titles of Wikipedia page links on a page.

        .. note:: Only includes articles from namespace 0, meaning no Category, User talk, or other meta-Wikipedia pages.

        .. note:: MediaWiki version >= 1.13
        '''
        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_links', False):
            self._links = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 13]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.13", 'links')

            self._links = list()
            for link in self.__continued_query({'prop': 'links', 'plnamespace': 0, 'pllimit': 'max'}):
                self._links.append(link['title'])

        return self._links

    @property
    def categories(self):
        '''
        List of non-hidden categories of a page.

        .. note:: MediaWiki version >= 1.14
        '''
        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_categories', False):
            self._categories = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 14]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.14", 'categories')

            self._categories = list()
            for link in self.__continued_query({'prop': 'categories', 'cllimit': 'max', 'clshow': '!hidden'}):
                if link['title'].startswith('Category:'):
                    self._categories.append(link['title'][9:])
                else:
                    self._categories.append(link['title'])

        return self._categories

    @property
    def redirects(self):
        '''
        List of all redirects to the page.

        .. note:: MediaWiki version >= 1.24
        '''
        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_redirects', False):
            self._redirects = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 24]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.24", 'redirects')

            self._redirects = list()
            for link in self.__continued_query({'prop': 'redirects','rdprop': 'title','rdlimit': '100'}):
                self._redirects.append(link['title'])

        return self._redirects

    @property
    def backlinks(self):
        '''
        List all pages that link to this page

        .. note:: Only includes articles from namespace 0, meaning no Category, User talk, or other meta-Wikipedia pages.

        .. note:: MediaWiki version >= 1.9
        '''
        global WIKIPEDIA_GLOBALS
        if not getattr(self, '_backlinks', False):
            self._backlinks = None

            if _cmp_major_minor(WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'], [1, 9]):
                raise WikipediaAPIVersionError(WIKIPEDIA_GLOBALS['API_URL'], WIKIPEDIA_GLOBALS['API_VERSION'], "1.9", 'backlinks')

            query_params = {
                'action': 'query',
                'list': 'backlinks',
                'bltitle': self.title,
                'bllimit': 500, # as many as possible
                'blfilterredir': 'nonredirects',
                'blcontinue': dict(),
                'blnamespace': 0
            }
            self._backlinks = list()
            while True: # mimic the __continued_query function
                results = _wiki_request(query_params)
                for link in results['query']['backlinks']:
                    self._backlinks.append(link['title'])
                if results.get('continue', False) is False:
                    break
                else:
                    query_params['blcontinue'] = results['continue']['blcontinue']
        return self._backlinks

    @property
    def sections(self):
        '''
        List of section titles from the table of contents on the page.
        '''

        if not getattr(self, '_sections', False):
            query_params = {
                'action': 'parse',
                'prop': 'sections',
            }
            if not getattr(self, 'title', None):
                query_params['pageid'] = self.pageid
            else:
                query_params['page'] = self.title
            request = _wiki_request(query_params)
            self._sections = [section['line'] for section in request['parse']['sections']]

        return self._sections

    def section(self, section_title):
        '''
        Get the plain text content of a section from `self.sections`.
        Returns None if `section_title` isn't found, otherwise returns a whitespace stripped string.

        This is a convenience method that wraps self.content.

        .. warning:: Calling `section` on a section that has subheadings will NOT return
                     the full text of all of the subsections. It only gets the text between
                     `section_title` and the next subheading, which is often empty.
        '''

        section = u"== {0} ==".format(section_title)
        try:
            index = self.content.index(section) + len(section)
        except ValueError:
            return None

        try:
            next_index = self.content.index("==", index)
        except ValueError:
            next_index = len(self.content)

        return self.content[index:next_index].lstrip("=").strip()

def _get_site_info():
    '''
    Parse out the Wikimedia site information including API Version and Extensions
    '''
    global WIKIPEDIA_GLOBALS
    response = _wiki_request({
        'meta': 'siteinfo',
        'siprop': 'extensions|general'
    })
    WIKIPEDIA_GLOBALS['API_VERSION'] = response['query']['general']['generator'].split(" ")[1].split("-")[0]
    major_minor = WIKIPEDIA_GLOBALS['API_VERSION'].split('.')
    for i, item in enumerate(major_minor):
        major_minor[i] = int(item)
    WIKIPEDIA_GLOBALS['API_VERSION_MAJOR_MINOR'] = major_minor
    WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS'] = set()
    for ext in response['query']['extensions']:
        WIKIPEDIA_GLOBALS['INSTALLED_EXTENSIONS'].add(ext['name'])

@cache
def languages():
    '''
    List all the currently supported language prefixes (usually ISO language code).

    Can be inputted to `set_lang` to change the Mediawiki that `wikipedia` requests
    results from.

    Returns: dict of <prefix>: <local_lang_name> pairs. To get just a list of prefixes,
    use `wikipedia.languages().keys()`.
    '''
    response = _wiki_request({
        'meta': 'siteinfo',
        'siprop': 'languages'
    })

    languages = response['query']['languages']

    return {
        lang['code']: lang['*']
        for lang in languages
    }


def donate():
    '''
    Open up the Wikimedia donate page in your favorite browser.
    '''
    import webbrowser

    webbrowser.open('https://donate.wikimedia.org/w/index.php?title=Special:FundraiserLandingPage', new=2)


def _wiki_request(params):
    '''
    Make a request to the Wikipedia API using the given search parameters.
    Returns a parsed dict of the JSON response.
    '''
    global WIKIPEDIA_GLOBALS

    rate_limit = WIKIPEDIA_GLOBALS['RATE_LIMIT']
    last_call = WIKIPEDIA_GLOBALS['RATE_LIMIT_LAST_CALL']
    wait = WIKIPEDIA_GLOBALS['RATE_LIMIT_MIN_WAIT']
    url = WIKIPEDIA_GLOBALS['API_URL']

    params['format'] = 'json'
    if not 'action' in params:
        params['action'] = 'query'

    if rate_limit and last_call and last_call + wait > datetime.now():
        # it hasn't been long enough since the last API call
        # so wait until we're in the clear to make the request
        wait_time = (last_call + wait) - datetime.now()
        time.sleep(int(wait_time.total_seconds()))
        disambiguation = list()
        for lis_item in filtered_lis:
            one_disambiguation = dict()
            item = lis_item.find_all("a")[0]
            if item:
                one_disambiguation["title"] = item["title"]
                one_disambiguation["description"] = lis_item.text
                disambiguation.append(one_disambiguation)
    if WIKIPEDIA_GLOBALS['SESSION'] is None:
        reset_session()

    r = WIKIPEDIA_GLOBALS['SESSION'].get(url, params=params, timeout=WIKIPEDIA_GLOBALS['TIMEOUT'])

    if rate_limit:
        WIKIPEDIA_GLOBALS['RATE_LIMIT_LAST_CALL'] = datetime.now()

    return r.json()
