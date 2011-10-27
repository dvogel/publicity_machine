#!/usr/bin/env python

import lxml.html
import re
import urllib2
from pprint import pprint
import datetime
import logging
from optparse import OptionParser
import feedparser
import time

from urllib2helpers import CacheHandler
import util
from store import Store

# eg
# "EAST PEORIA, Ill., Oct. 24, 2011 /PRNewswire/ -- "
# "NUEVA YORK, 26 de octubre de 2011 /PRNewswire-HISPANIC PR WIRE/ --"
dateline_pat = re.compile(r'^\s*(?P<location>.*?),\s*(?P<month>\w{3,})[.]?\s*(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s*/(?P<wire>.*?)/\s*--\s*',re.MULTILINE)

# eg "SOURCE blahcorp inc."
source_pat = re.compile(r'^(?:SOURCE|FUENTE)\s+(?P<source>.*?)\s*$',re.MULTILINE)

# cruft elements to strip before extracting text (don't forget the commas!)
cruft_sel = 'script, style, .newsreldettrans, .horizontalline, .clearboth, #dvWideRelease, #linktopagetop'



# output fields:
# url
# date  - unix timestamp
# title
# company
# text
# topics    - comma-separated topics
# location
# language - 'en_us', 'fr', 'es' etc...
def extract(html, url):

    out = {'url':url}

    doc = lxml.html.fromstring(html)
    doc.make_links_absolute(base_url=url)

    topics = set()
    topics_div = doc.cssselect('.col-1 .seo-h4-seemorereleases')[0]
    for a in topics_div.findall('a'):
        topic = unicode(a.get('title')).strip()
        topic = re.sub(',','',topic)    # kill commas
        topics.add(topic)
    out['topics'] = u','.join(topics)

    # "<meta http-equiv='Content-Language' content='es'/>"
    lang_meta = doc.cssselect('meta[http-equiv="Content-Language"]')[0]
    out['language'] = unicode(lang_meta.get('content')).lower()

    # use title to identify div containing main content text
    head = doc.cssselect('#dvHead')[0]
    main = head.getparent()
    out['title'] = unicode(head.text_content()).strip()

    # grab text
    [cruft.drop_tree() for cruft in main.cssselect(cruft_sel)]
    content = util.render_text(main)
    content = re.compile(r'[\t ]{1,}',re.DOTALL).sub(' ',content)
    content = re.compile(r'\s{2,}$',re.MULTILINE).sub('\n',content)
    out['text'] = content

    # eg "SOURCE blahcorp inc."
    m = source_pat.search(content)
    if m:
        out['company'] = m.group('source')
    else:
        out['company'] = u''

    # break up dateline
    m = dateline_pat.search(content)
    if m:
        year = int(m.group('year'))
        month = util.lookup_month(m.group('month'))
        day = int(m.group('day'))
        pubdate = datetime.date(year,month,day)
        location = m.group('location')
    else:
        # TODO: handle non-english dates
        pubdate = datetime.datetime.now()
        location = u''

    out['date'] = int(time.mktime(pubdate.timetuple())*1000)
    out['location'] = location
    return out



# TODO: factor out the structural stuff into a tidy base class
def main():
    parser = OptionParser(usage="%prog: [options]")
    parser.add_option('-v', '--verbose', action='store_true')
    parser.add_option('-d', '--debug', action='store_true')
    (options, args) = parser.parse_args()

    log_level = logging.ERROR
    if options.debug:
        log_level = logging.DEBUG
    elif options.verbose:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)    #, format='%(message)s')

    store = Store("prnewswire", doc_type=1)

    opener = urllib2.build_opener(CacheHandler(".cache"))
    urllib2.install_opener(opener)

    feed_url = "http://www.prnewswire.com/rss/all-news-releases-from-PR-newswire-news.rss"

    logging.debug("read feed %s", feed_url)
    feed = feedparser.parse(feed_url)
    all_urls = [e.link for e in feed.entries]
    # cull out ones we've got
    urls = [url for url in all_urls if not store.already_got(url)]
    logging.info("feed yields %d urls (%d are new)", len(all_urls),len(urls))

    err_cnt = 0
    try:

        for url in urls:
            try:
                if store.already_got(url):
                    logging.debug("got %s",url)
                else:
                    logging.debug("fetch %s",url)
                    response = urllib2.urlopen(url)
                    html = response.read()

                    # TODO: maybe just skip ones which redirect to other domains?
                    if response.geturl() != url:
                        logging.warning("Redirect detected %s => %s",url,response.geturl())
                    press_release = extract(html, url)

                    # encode text fields
                    for f in ('url','title','company','text','location','language','topics'):
                        press_release[f] = press_release[f].encode('utf-8')
                    store.add(press_release)
            except Exception as e:
                logging.error("failed on %s: %s %s",url,e.__class__,e)
                err_cnt += 1
    finally:
        store.save()



    #test_url = "http://www.prnewswire.com/news-releases/robert-gates-joins-federal-companies-as-general-counsel-and-vice-president-of-human-resources-132446423.html"
    # this one has tables of figures
#    test_url = "http://www.prnewswire.com/news-releases/staar-surgical-reports-16-third-quarter-revenue-growth-132482743.html"

main()

