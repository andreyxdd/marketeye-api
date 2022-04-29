"""
Scraping for tickers news section of the marketwatch website
"""

import scrapy
import reticker


class MarketwatchSpider(scrapy.Spider):
    """
    MarketwatchSpider is an extension of the scrapy.Spider class.
    """

    name = "marketwatch-spider"

    start_urls = ["https://www.marketwatch.com/"]

    def parse(self, response):
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            title: the title of the post
            link: the url to the page that post refers to
        }
        """

        # list of hrefs (to article pages) found on the page
        suburls = []
        # will be concatenated

        suburls += response.css("h3.article__headline a::attr(href)").getall()

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

        # scraping title
        content = " ".join(
            response.css('a.qt-chip-referenced span.symbol::text').getall()
        ).strip()

        '''
        # scraping article text
        content += " ".join(response.css("article p::text").getall()).strip()

        # scraping text in 'strong'
        content += " ".join(response.css("p strong::text").getall()).strip()

        # scraping the tickers in the side-bar last news section
        content += " ".join(response.css("a span::text").getall()).strip()
        '''

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
