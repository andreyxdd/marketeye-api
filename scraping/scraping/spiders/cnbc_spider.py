"""
Initial attempt to scrape the cnbc home page
"""

import scrapy
import reticker


class CNBCSpider(scrapy.Spider):
    """
    CNBCSpider is an extension of the scrapy.Spider class.
    """

    name = "cnbc-spider"

    start_urls = ["https://www.cnbc.com/"]

    def parse(self, response):
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            title: the title of the post
            link: the url to the page that post refers to
        }
        """

        suburls = response.css("div.SecondaryCard-headline a::attr(href)").getall()

        # list concatenation
        suburls += response.css("div.RiverHeadline-headline a::attr(href)").getall()
        suburls += response.css("a.Card-title::attr(href)").getall()

        for suburl in suburls:
            if suburl.startswith("https://www.cnbc.com/"):  # make sure it is url
                yield scrapy.Request(url=suburl, callback=self.parse_article_page)

    def parse_article_page(self, response):  # pylint: disable=R0201
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            url: the link to the article's page
            tickers: the list of tickers found in the page content
        }
        """

        # scraping text from the key points section
        content = " ".join(response.css("div.group ul li::text").getall()).strip()

        # scraping article text content
        content += " ".join(response.css("div.group p::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
