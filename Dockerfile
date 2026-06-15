FROM python:3.14.3-bookworm

WORKDIR /bot

COPY ./src .

# install python dependencies
RUN pip install --no-cache-dir -r ./resources/requirements.txt

CMD ["python", "bot.py"]

