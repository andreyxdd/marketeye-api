"""
Scraping for tickers news section of the morningstar website
"""

import scrapy
import reticker


class MorningstarSpider(scrapy.Spider):
    """
    MorningstarSpider is an extension of the scrapy.Spider class.
    """

    name = "morningstar-spider"

    start_urls = [
        "https://www.morningstar.com/",
        "https://www.morningstar.com/topics/sustainable-investing",
        "https://www.morningstar.com/funds",
        "https://www.morningstar.com/stocks",
        "https://www.morningstar.com/bonds",
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

        suburls += response.css("a.mdc-grid-item__title--link::attr(href)").getall()

        # removig duplicates
        suburls = list(dict.fromkeys(suburls))

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

        # scraping mentioned tickers
        content = " ".join(
            [
                s.replace("\n", "")
                .replace("\xa0", "")
                .replace("\t", "")
                .replace("(", "")
                .replace(")", "")
                for s in response.css("a.mds-link--no-underline::text").getall()
            ]
        ).strip()

        # scraping text paragraphs
        content += " ".join(response.css("p::text").getall()).strip()

        tickers = reticker.TickerExtractor().extract(content)

        yield {"url": response.url, "tickers": tickers}
