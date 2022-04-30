"""
Scraping for tickers news section of the motley-fool website
"""

import scrapy
import reticker


class FoolSpider(scrapy.Spider):
    """
    FoolSpider is an extension of the scrapy.Spider class.
    """

    name = "fool-spider"

    start_urls = [
        "https://www.fool.com/investing-news/?page=" + str(i) for i in range(1, 11)
    ]

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

        suburls += response.css("div.content-block a::attr(href)").getall()
        suburls += response.css(
            "div.content-block.listed-articles a::attr(href)"
        ).getall()

        # removig duplicates
        suburls = list(dict.fromkeys(suburls))

        for suburl in suburls:
            if suburl.startswith("/investing"):
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

        # scraping titles
        content = " ".join(response.css("h1::text").getall()).strip()
        content += " ".join(response.css("h2::text").getall()).strip()

        # scraping text paragraphs
        content += " ".join(response.css("p::text").getall()).strip()

        # scraping text in 'spans' (usually tickers)
        content += " ".join(response.css("p span a::text").getall()).strip()

        # scraping the tickers in the side-bar last news section
        content += " ".join(response.css("h2 a::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
