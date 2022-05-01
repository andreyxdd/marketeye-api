"""
Scraping CNN website for tickers
"""

import scrapy
import reticker


class CNNSpider(scrapy.Spider):
    """
    CNNSpider is an extension of the scrapy.Spider class.
    """

    name = "cnn-spider"

    start_urls = [
        "https://www.cnn.com/business",
        "https://www.cnn.com/business/success",
        "https://www.cnn.com/business/perspectives",
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

        # cnn.com/business/...
        suburls += response.css("h3.cd__headline a::attr(href)").getall()

        for suburl in suburls:
            # make sure it's not a url video
            if (
                not suburl.startswith("/videos")
                and suburl.find("cnn-underscored") == -1
                and suburl.find("fool") == -1
            ):
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

        # scraping article text in paragraphs
        content = " ".join(
            response.css("div.zn-body__paragraph::text").getall()
        ).strip()
        content += " ".join(response.css("p::text").getall()).strip()

        # scraping links text in spans
        content += " ".join(response.css("a.inlink::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
