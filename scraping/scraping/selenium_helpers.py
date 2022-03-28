"""
    Module with helper-functions based on the selenium
"""

import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from webdriver_manager.chrome import ChromeDriverManager


def find_links_after_scroll(base_url, class_name_to_search):
    """
    Function that scrolls to the bottom of the web page (by base_url)
    and that looks for all the needed hrefs

    Args:
        base_url (string):
            url to search for links after scrolling to bottom
        class_name_to_search (string):
            css class name of an element with href attribute

    Returns:
        list of strings (links to news articles)
    """
    # initializing selenium driver
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.get(base_url)

    # scroll settings
    scroll_to = 10000
    sleep_time = 1
    news_blocks = 0
    n_blocks = 0

    while True:
        # force browser to scroll, update scroll heigth, and wait
        driver.execute_script(f"window.scrollTo(0,{scroll_to});")
        time.sleep(sleep_time)
        scroll_to += scroll_to

        # getting all the new blocks
        news_blocks = driver.find_elements(by=By.CLASS_NAME, value=class_name_to_search)

        # break while-loop if # of blocks is the same
        if len(news_blocks) == n_blocks:
            break

        # esle - update the number of blocks
        n_blocks = len(news_blocks)

    # once the scroll is at the bottom, find all hrefs
    links = []
    for block in news_blocks:
        href = block.get_attribute("href")
        links.append(href)

    driver.quit()

    return links
