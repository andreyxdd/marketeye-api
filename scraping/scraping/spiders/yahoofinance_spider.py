"""
Scraping the yahoo.finance home and news pages
"""

import scrapy
import reticker

from scraping.selenium_helpers import find_links_after_scroll

untickers = [
    "SYMBOL",
    "POST",
    "PRE",
    "DELETE",
    "CUSTOM",
    "CLOSE",
    "DIVE",
    "DEEP",
    "US",
    "AM",
    "PM",
    "CANCEL",
    "DONE",
    "CRYPTO",
    "CAD",
    "USD",
    "LONDON",
]


def check_ticker(ticker):
    """
    Helper function to check if the ticker indeed a ticker
    """
    if ticker in untickers:
        return False

    return True


class YahoofinanceSpider(scrapy.Spider):
    """
    YahoofinanceSpider is an extension of the scrapy.Spider class.
    """

    name = "yahoo.finance-spider"

    start_urls = ["https://finance.yahoo.com/", "https://finance.yahoo.com/news/"]

    def parse(self, response):
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            title: the title of the post
            link: the url to the page that post refers to
        }
        """

        suburls = find_links_after_scroll(response.url, "js-content-viewer")

        for suburl in suburls:
            yield scrapy.Request(response.urljoin(suburl), self.parse_article_page)

    def parse_article_page(self, response):  # pylint: disable=R0201
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            url: the link to the article's page
            tickers: the list of tickers found in the page content
        }
        """

        # scraping text from all paragraph tags
        content = " ".join(response.css("p::text").getall()).strip()

        # scraping "pill" element with the ticker (if exists)
        content += " ".join(
            response.css("span.xray-entity-title-link::text").getall()
        ).strip()

        # scraping elements on the right side-bar that
        # show related and recent quotes (if exists)
        content += " ".join(response.css("a[href^='/quote/']::text").getall())

        tickers = list(
            filter(check_ticker, reticker.TickerExtractor().extract(content))
        )

        yield {"url": response.url, "tickers": tickers}
