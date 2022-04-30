"""
Scraping cnbc website for tickers
"""

import scrapy
import reticker


class CNBCSpider(scrapy.Spider):
    """
    CNBCSpider is an extension of the scrapy.Spider class.
    """

    name = "cnbc-spider"

    start_urls = [
        "https://www.cnbc.com/",
        "https://www.cnbc.com/markets/",
        "https://www.cnbc.com/business/",
        "https://www.cnbc.com/investing/",
        "https://www.cnbc.com/technology/",
        "https://www.cnbc.com/politics/",
        "https://www.cnbc.com/investingclub/",
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

        # cnbc.com/
        suburls += response.css("div.SecondaryCard-headline a::attr(href)").getall()
        suburls += response.css("div.RiverHeadline-headline a::attr(href)").getall()
        suburls += response.css("a.Card-title::attr(href)").getall()

        # cnbc.com /markets | /business | /investing so on ...
        suburls += response.css("div.Card-titleContainer a::attr(href)").getall()
        suburls += response.css("div.Card-standardBreakerCard a::attr(href)").getall()

        for suburl in suburls:
            if suburl.startswith("https://www.cnbc.com/"):  # make sure it's url
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

        # cnbc.com/video
        content += " ".join(response.css("h1::text").getall()).strip()
        content += " ".join(
            response.css(".ClipPlayer-clipPlayerIntroSummary::text").getall()
        ).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
