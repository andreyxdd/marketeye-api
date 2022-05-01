"""
Scraping for tickers news section of the tipranks website
"""

import scrapy
import reticker


class TipranksSpider(scrapy.Spider):
    """
    TipranksSpider is an extension of the scrapy.Spider class.
    """

    name = "tipranks-spider"

    start_urls = ["https://www.tipranks.com/news/category/news"]

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

        suburls += response.css(
            "div.w12.displayflex.hoverOpacity80.mb6.mobile_mb5 a::attr(href)"
        ).getall()

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
        content = " ".join(response.css("h1::text").getall()).strip()

        # scraping article text
        content += " ".join(response.css("article p::text").getall()).strip()

        # scraping text in 'strong'
        content += " ".join(response.css("p strong::text").getall()).strip()

        # scraping the tickers in the side-bar last news section
        content += " ".join(response.css("a span::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
