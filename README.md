# Template starter project based on FastAPI and MongoDB

## Structure

- api: for implementing endpoints
- core: general settings of the project, i.e. initiating environmental variables
- db: for establishing a connection to MongoDB and implementing methods for CRUD operations
- utils: general utility folder, e.g. useful methods to handle date-time objects and sending emails (via smtplib)
- ```main.py```: script to initiate the server, open/close connection to db

## Launching
First, initiate the virtual environment in the root folder. Then install all the necessary packages with:
```
pip install -r requirements.txt
```
Then start the FastAPI app with:
```
uvicorn main:app --reload
```

## Linting
The ```pylint``` is selected as a default linter. To avoid certain warnings, adjust settings of ```.pylintrc``` in the root folder.
Currently, the following warnings are ignored:
- ```E1136``` relates to the issues with ```Optional``` and ```Union``` types from ```typings```
- ```E0401``` indicates erreneous importings
- ```E0402``` indicates erreneous relative importings

It is recommended to initiate the linter tool in the code editor. For example, in VSCode, press ```ctrl+shift+p```, search for ```Select linter``` and choose ```pylint```.

## Linting and pre-commit hooks

This template project also utilizes the pre-commit hooks (see ```.pre-commit-config.yaml``` for details). Besides running ```pylint``` in all files in the directory and subdirectories, the pre-commit hooks upgrade packages with ```pyupgrade``` and check code for formating with ```black```. To use pre-commit hooks, before committing, run:
```$ pre-commit install```
