# Market-Eye API

![Data Processing Cronjob](https://github.com/andreyxdd/marketeye-api/actions/workflows/cronjob.yml/badge.svg)

Market-Eye API provides methods for computing technical indicators of individual stocks (e.g. MACD, EMAs, MFI, etc.) as well as indicators describing the market as a whole (e.g. CVI, VIX, etc.). The EOD (end of the day) historical data is fetched from Nasdaq Data Link API. The only markets analyzed are NASDAQ and NYSE.

Furthermore, the API includes a scraping bot that collects the number of mentions of a given stock ticker. The scraping is done across some of the most popular news websites.

Finally, the API provides methods for sorting all the stock data and scraping results (for the given date) based on several implemented criteria.

## Deployment

The API is deployed on [Heroku](https://marketeye-api.herokuapp.com/). MongoDB handles data storage. Learn a bit more on the [documentation page](https://marketeye-api.herokuapp.com/docs).

## Codebase Structure

- *api*: for implementing endpoints
- *core*: general settings of the project, i.e. initiating environmental variables
- *db*: for establishing a connection to MongoDB and implementing methods for CRUD operations
- *utils*: general utility folder, e.g. useful methods to handle date-time objects and sending emails (via smtplib)
- ```main.py```: script to initiate the server, open/close connection to db
- .github/workflows: to run
  - the ```cronjob.py``` that fetches the EOD stock prices later to be used for calculations
  - the ```scraping.py``` that scrapes the stock tickers using [Scrapy](https://scrapy.org/) and [Selenium](https://selenium-python.readthedocs.io/)

### Running Locally

First, initiate the virtual environment in the root folder. Then install all the necessary packages with:
```
pip install -r requirements.txt
```
Then start the FastAPI app with:
```
uvicorn main:app --reload
```

### Linting
The ```pylint``` is selected as a default linter. To avoid certain warnings, adjust settings of ```.pylintrc``` in the root folder.
Currently, the following warnings are ignored:
- ```E1136``` relates to the issues with ```Optional``` and ```Union``` types from ```typings```
- ```E0401``` indicates erreneous importings
- ```E0402``` indicates erreneous relative importings
- ```R0801``` ignore similarities between files

It is recommended to initiate the linter tool in the code editor. For example, in VSCode, press ```ctrl+shift+p```, search for ```Select linter``` and choose ```pylint```.

### Pre-commit Hooks

This template project also utilizes the pre-commit hooks (see ```.pre-commit-config.yaml``` for details). Besides running ```pylint``` in all files in the directory and subdirectories, the pre-commit hooks upgrade packages with ```pyupgrade``` and check code for formating with ```black```. To use pre-commit hooks, before committing, run:
```
pre-commit install
```
