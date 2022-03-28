"""
Initial attempt to scrape the yahoo.finance home page
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

    name = "yahoo.finances-spider"

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

        content = "".join(response.css("div.caas-content").getall()).strip()

        tickers = list(
            filter(check_ticker, reticker.TickerExtractor().extract(content))
        )

        yield {"url": response.url, "tickers": tickers}
