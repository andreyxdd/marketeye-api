"""
It is simply an example of how to work with scrapy.
"""

import scrapy


class SampleSpider(scrapy.Spider):  # pylint: disable=R0903
    """
    Sample spider is an extension of the scrapy.Spider class.
    """

    name = "sample-spider"

    start_urls = ["https://www.scrapethissite.com/pages/"]

    def parse(self, response):  # pylint: disable=R0201
        """
        Parsing the response to each url in the start_urls

        Yields:
        {
            title: the title of the post
            link: the url to the page that post refers to
        }
        """

        for post in response.css("div.page"):
            yield {
                "title": post.css(".page-title a::text")[0].get(),
                "link": post.css(".page-title a::attr(href)")[0].get(),
            }
