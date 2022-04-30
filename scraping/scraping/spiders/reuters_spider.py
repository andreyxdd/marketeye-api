"""
Scraping for tickers market news section of the reuters website
"""

import scrapy
import reticker


class ReutersSpider(scrapy.Spider):
    """
    ReutersSpider is an extension of the scrapy.Spider class.
    """

    name = "reuters-spider"

    start_urls = [
        "https://www.reuters.com/markets/stocks",
        "https://www.reuters.com/markets/funds/",
        "https://www.reuters.com/markets/wealth/",
        "https://www.reuters.com/markets/rates-bonds/",
        "https://www.reuters.com/business/aerospace-defense/",
        "https://www.reuters.com/business/energy/",
        "https://www.reuters.com/business/autos-transportation/",
        "https://www.reuters.com/business/healthcare-pharmaceuticals/",
        "https://www.reuters.com/business/retail-consumer/",
        "https://www.reuters.com/business/sustainable-business/",
        "https://www.reuters.com/business/charged/",
        "https://www.reuters.com/business/future-of-health/",
        "https://www.reuters.com/business/future-of-money/",
        "https://www.reuters.com/business/take-five/",
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

        # list of hrefs (to article pages) found on each page above
        suburls = []

        # to concatenate
        suburls += response.css("div.story-card a::attr(href)").getall()

        # removig duplicates
        suburls = list(dict.fromkeys(suburls))

        for suburl in suburls:
            # make sure it's not a url video
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

        # formating content
        tmp = [
            s.replace("(", "").replace(")", "")
            for s in response.css("a.text__text__1FZLe::text").getall()
        ]
        tickers_tmp = []

        for elm in tmp:
            dot_splitted = [s for s in elm.split(".") if s]
            if len(dot_splitted) > 1 and dot_splitted[1] in ["O", "N"]:
                tickers_tmp.append(dot_splitted[0])

        # scraping mentioned tickers
        content = " ".join(tickers_tmp).strip()

        # scraping text paragraphs
        content += " ".join(response.css("p::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
